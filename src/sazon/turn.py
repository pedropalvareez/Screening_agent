"""The turn pipeline (decision 006): extract (LLM) -> validate (schema) -> rules and
next stage (engine) -> closed directive (code) -> phrase (LLM). The LLM never
decides.

turn() is the one entry point, so the web chat, voice and WhatsApp are adapters.
"""

import logging
import os
import re
import threading
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sazon import engine, prompts, storage, templates
from sazon.engine import ZONES, Outcome, Reason, Screening, resolve_zone
from sazon.llm import FAILURES, LLM, OpenRouter
from sazon.schema import Extraction, ScreeningFields, Strict
from sazon.storage import Closing, Conversation, Line, PoolConsent
from sazon.templates import say

log = logging.getLogger(__name__)

POOL_CONSENT = timedelta(days=365)  # decision 018
TIMEZONES = {"ES": ZoneInfo("Europe/Madrid"), "MX": ZoneInfo("America/Mexico_City")}
# The service cities by country: tap options when the zone is asked again (007).
CITIES: dict[str, list[str]] = {
    country: [city for city, zone in ZONES.items() if zone.country == country]
    for country in dict.fromkeys(zone.country for zone in ZONES.values())
}
# shortcut: regexes miss unusual formats (decision 014); a PII detection service is
# the upgrade. Order matters: cards before phones, and a leading 00 is a phone.
REDACTIONS = {
    "[email]": re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"),
    "[CURP]": re.compile(r"\b[A-Z]{4}\d{6}[HMX][A-Z]{5}[A-Z\d]\d\b", re.IGNORECASE),
    "[DNI/NIE]": re.compile(
        r"\b(?:\d{8}|[XYZ][\s-]?\d{7})[\s-]?[A-Z]\b", re.IGNORECASE
    ),
    "[card]": re.compile(r"\b(?!00)(?:\d[\s-]?){12,18}\d\b"),
    "[phone]": re.compile(r"(?:(?:\+|\b00)\d{1,3}[\s.-]?|\b)(?:\d[\s.-]?){8,9}\d\b"),
}
# shortcut: in-process locks, so two quick messages from one candidate run one
# after the other; a second worker process needs the lock in the database.
LOCKS = [threading.Lock() for _ in range(64)]


class Reply(Strict):
    text: str
    options: dict[str, list[str]] | None = None  # CITIES, when the zone is re-asked


@dataclass(frozen=True)
class Agent:
    """What a turn needs: the LLM and the SQLite file."""

    llm: LLM
    db: Path


class UnknownConversation(LookupError):
    pass


def connect() -> Agent:
    """The production agent, built once at startup: a missing OPENROUTER_API_KEY
    or an unwritable DB_PATH fails there, not on the first candidate."""
    llm = OpenRouter()
    db = Path(os.environ.get("DB_PATH", "sazon.db"))
    storage.create(db)
    return Agent(llm, db)


def redact(text: str) -> str:
    for label, pattern in REDACTIONS.items():
        text = pattern.sub(label, text)
    return text


def start(agent: Agent, now: datetime) -> tuple[str, Reply]:
    """Open a conversation: the agent writes first (decisions 004, 020)."""
    conversation = Conversation(
        id=uuid.uuid4().hex,  # the only key to the chat, so it must not be guessable
        created_at=now,
        language="es",
        screening=Screening(last_message_at=now),
        transcript=[Line(at=now, role="agent", text=templates.GREETING)],
    )
    storage.save(agent.db, conversation)
    return conversation.id, Reply(text=templates.GREETING)


def turn(agent: Agent, conversation_id: str, message: str, now: datetime) -> Reply:
    """One candidate message in, one reply out. Personal data is redacted before
    the LLM or storage sees it, and the conversation is saved every turn."""
    text = redact(message)
    with LOCKS[hash(conversation_id) % len(LOCKS)]:
        conversation = storage.load(agent.db, conversation_id)
        if conversation is None:
            raise UnknownConversation(conversation_id)
        conversation.transcript.append(Line(at=now, role="candidate", text=text))
        reply = respond(agent.llm, conversation, text, now)
        conversation.transcript.append(Line(at=now, role="agent", text=reply.text))
        storage.save(agent.db, conversation)
    return reply


def respond(llm: LLM, c: Conversation, text: str, now: datetime) -> Reply:
    """Changes c only when the LLM calls succeed: a failure leaves the state as
    it was (decision 006)."""
    if c.closing is not None:
        return after_close(llm, c, c.closing, text, now)
    pending = prompts.QUESTIONS[engine.stage(c.screening)]
    today = local_date(c.screening.fields, now)
    try:
        extraction = llm.extract(
            prompts.extraction(pending, last_said(c), c.language, today, text)
        )
    except FAILURES as error:
        return failed(c, error)
    if extraction.language == "other":
        return Reply(text=templates.OTHER_LANGUAGE)
    state = engine.apply(c.screening, extraction, now, today)
    result = engine.outcome(state, now)
    if result is None:
        try:
            reply = ask(llm, c.screening, state, extraction)
        except FAILURES as error:
            return failed(c, error)
    else:
        c.closing = close(llm, c, state, result, now)
        reply = Reply(text=say(templates.CLOSINGS[result], extraction.language))
    c.screening, c.language = state, extraction.language
    if extraction.question == "other":
        c.questions.append(text)
    return reply


def ask(llm: LLM, before: Screening, after: Screening, extraction: Extraction) -> Reply:
    """The next question, worded by the LLM from a closed directive, after the
    code-approved answer to anything the candidate asked."""
    stage = engine.stage(after)
    invalid = after.invalid_answers.get(stage, 0)
    uncovered = stage == "zone" and after.uncovered_zones > 0
    cities = uncovered or (stage == "zone" and invalid >= 2)
    directive = prompts.directive(
        stage,
        heard=heard(before.fields, after.fields),
        invalid=invalid,
        cities=cities,
        uncovered=uncovered,
        recap=templates.key_data(after.fields),
    )
    language = extraction.language
    phrased = llm.phrase(prompts.phrasing(language, country(after.fields), directive))
    approved: list[tuple[str, str]] = []
    if extraction.intent == "abusive":  # the first: the second closed the screening
        approved.append(templates.WARNING)
    if extraction.question is not None:
        approved.append(templates.ANSWERS[extraction.question])
    text = " ".join([*(say(a, language) for a in approved), phrased])
    return Reply(text=text, options=CITIES if cities else None)


def close(
    llm: LLM,
    c: Conversation,
    state: Screening,
    result: tuple[Outcome, Reason | None],
    now: datetime,
) -> Closing:
    """Freeze the outcome and write the summary (decision 013). If the notes fail,
    the summary keeps the key data and the candidate still gets the closing."""
    try:
        written = llm.phrase(prompts.notes(c.transcript))
    except FAILURES as error:
        log.warning("summary notes failed in %s: %s", c.id, type(error).__name__)
        written = ""
    notes = [note for line in written.splitlines() if (note := line.strip(" -•*"))]
    outcome, reason = result
    return Closing(
        at=now,
        outcome=outcome,
        reason=reason,
        flagged=engine.flagged(state),
        summary=templates.summary(state, outcome, reason, notes[:3]),
    )


def after_close(
    llm: LLM, c: Conversation, closing: Closing, text: str, now: datetime
) -> Reply:
    """A closed screening only takes the talent-pool opt-in (decision 018); any
    other message is flagged for a person (process-design §2)."""
    city = c.screening.fields.zone
    if (
        closing.reason == "zone_not_covered"
        and c.pool is None
        and not c.wrote_after_close
        and city is not None
    ):
        today = local_date(c.screening.fields, now)
        try:
            extraction = llm.extract(
                prompts.extraction(prompts.POOL, last_said(c), c.language, today, text)
            )
        except FAILURES as error:
            return failed(c, error)
        if extraction.confirmed is True:
            c.pool = PoolConsent(at=now, expires_on=today + POOL_CONSENT, city=city)
            return Reply(text=say(templates.POOL_YES, c.language))
        if extraction.confirmed is False:
            return Reply(text=say(templates.POOL_NO, c.language))
    c.wrote_after_close = True
    return Reply(text=say(templates.AFTER_CLOSE, c.language))


def failed(c: Conversation, error: Exception) -> Reply:
    """The LLM failed twice (llm.py retries once): ask again (decision 006)."""
    # The type only: the error holds the model's raw reply, which can quote the
    # candidate (decision 014).
    log.warning("LLM failed in %s: %s", c.id, type(error).__name__)
    return Reply(text=say(templates.SAY_AGAIN, c.language))


def heard(before: ScreeningFields, after: ScreeningFields) -> str:
    """The key-data lines this message set or changed, for the LLM to acknowledge:
    the zone shows its service city, so the LLM has nothing to double-check."""
    old = templates.key_data(before).splitlines()
    return "; ".join(
        line
        for line in templates.key_data(after).splitlines()
        if line not in old and not line.endswith(templates.NOT_GIVEN)
    )


def last_said(c: Conversation) -> str:
    return next(line.text for line in reversed(c.transcript) if line.role == "agent")


def country(fields: ScreeningFields) -> str | None:
    """The candidate's country, once their zone resolves to a service city."""
    city = None if fields.zone is None else resolve_zone(fields.zone)
    return None if city is None else ZONES[city].country


def local_date(fields: ScreeningFields, now: datetime) -> date:
    """The candidate's date, which the engine needs (not the server's): Spain's
    until the zone is known."""
    return now.astimezone(TIMEZONES[country(fields) or "ES"]).date()
