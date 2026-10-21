"""Business rules: derived stage, knockouts, outcomes and zone coverage.

Pure functions, no LLM and no clock: callers pass `now` and `today`. The only I/O
is reading config/zones.toml once, at import.
"""

import difflib
import tomllib
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, Field, TypeAdapter

from sazon.schema import Extraction, Question, ScreeningFields, Strict

Stage = Literal[
    "greeting",
    "license",
    "zone",
    "name",
    "availability",
    "schedule",
    "experience",
    "start_date",
    "confirm",
]
Outcome = Literal["qualified", "needs_review", "disqualified", "withdrawn", "abandoned"]
Reason = Literal["no_license", "zone_not_covered", "abusive"]
# The hiring decision stays with a recruiter, apart from the outcome (012, 017).
RecruiterStatus = Literal[
    "pending", "contacted", "hired", "rejected", "showed_up", "no_show"
]

# Field stages in asking order, each with the ScreeningFields attribute it fills.
FIELD_STAGES: dict[Stage, str] = {
    "license": "has_license",
    "zone": "zone",
    "name": "full_name",
    "availability": "availability",
    "schedule": "preferred_schedule",
    "experience": "prior_delivery_experience",
    "start_date": "start_date",
}
MAX_INVALID_ANSWERS = 3
START_WINDOW = timedelta(days=365)
ABANDON_AFTER = timedelta(hours=72)
# shortcut: one typo in a name of 7+ letters matches, and so does a real uncovered
# town one letter away (Palencia -> Valencia); CONFIRM shows the city back.
# Postcode distance is the production fix (decision 007).
ZONE_MATCH_CUTOFF = 0.85


class Zone(Strict):
    country: Literal["ES", "MX"]
    aliases: list[str]


ZONES_FILE = Path(__file__).resolve().parents[2] / "config" / "zones.toml"
ZONES = TypeAdapter(dict[str, Zone]).validate_python(
    tomllib.loads(ZONES_FILE.read_text(encoding="utf-8"))["zones"]
)


def normalize(text: str) -> str:
    """Lowercase, accents stripped: "Málaga" -> "malaga"."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


# Every listed spelling, normalized, to its service city.
CITY_BY_NAME = {
    normalize(name): city
    for city, zone in ZONES.items()
    for name in (city, *zone.aliases)
}


def resolve_zone(raw: str) -> str | None:
    """The service city for a city as written, or None when it is not covered."""
    name = normalize(raw)
    if name in CITY_BY_NAME:
        return CITY_BY_NAME[name]
    close = difflib.get_close_matches(name, CITY_BY_NAME, n=1, cutoff=ZONE_MATCH_CUTOFF)
    return CITY_BY_NAME[close[0]] if close else None


class Screening(Strict):
    """Conversation state. The stage and outcome are derived from it, never stored."""

    # the candidate's last message; before the first one, when the greeting was sent
    last_message_at: AwareDatetime
    fields: ScreeningFields = ScreeningFields()
    started: bool = False
    confirmed: bool = False
    withdrawn: bool = False
    abusive_messages: int = 0
    uncovered_zones: int = 0  # answers naming a city outside the service area
    invalid_answers: dict[Stage, int] = Field(default_factory=dict[Stage, int])
    # For the summary (013): valid answers a later message changed, in stage order,
    # and the topic of every question asked.
    corrected: list[Stage] = Field(default_factory=list[Stage])
    topics: list[Question] = Field(default_factory=list[Question])


def missing(fields: ScreeningFields, stage: Stage) -> bool:
    """A field stage still unanswered. A zone counts once it resolves to a city."""
    if stage == "zone":
        return fields.zone is None or resolve_zone(fields.zone) is None
    return getattr(fields, FIELD_STAGES[stage]) is None


def flagged(state: Screening) -> list[Stage]:
    """Field stages still unanswered after MAX_INVALID_ANSWERS invalid answers."""
    return [
        stage
        for stage in FIELD_STAGES
        if missing(state.fields, stage)
        and state.invalid_answers.get(stage, 0) >= MAX_INVALID_ANSWERS
    ]


def stage(state: Screening) -> Stage:
    """First unmet requirement. A flagged field counts as met, so the screening
    moves on."""
    if not state.started:
        return "greeting"
    skipped = flagged(state)
    for s in FIELD_STAGES:
        if missing(state.fields, s) and s not in skipped:
            return s
    return "confirm"


def outcome(state: Screening, now: datetime) -> tuple[Outcome, Reason | None] | None:
    """None while the screening is open. ABANDONED is computed on read."""
    if state.withdrawn:
        return ("withdrawn", None)
    if state.abusive_messages >= 2:
        return ("withdrawn", "abusive")
    if state.fields.has_license is False:
        return ("disqualified", "no_license")
    if state.uncovered_zones >= 2:  # one re-ask first
        return ("disqualified", "zone_not_covered")
    if state.confirmed:
        return ("needs_review", None) if flagged(state) else ("qualified", None)
    if now - state.last_message_at >= ABANDON_AFTER:
        return ("abandoned", None)
    return None


def reopened(closed: Outcome) -> Outcome:
    """A recruiter reopens a DISQUALIFIED candidate for review (process-design §2)."""
    if closed != "disqualified":
        raise ValueError(f"only a disqualified candidate can be reopened, not {closed}")
    return "needs_review"


def apply(
    state: Screening, extraction: Extraction, now: datetime, today: date
) -> Screening:
    """Fold one candidate message into the state. A closed screening stays as is;
    an abandoned one resumes where it stopped.

    `today` is the candidate's local date, not now.date(): near midnight UTC
    differs from Mexico's date.
    """
    closed = outcome(state, now)
    if closed is not None and closed[0] != "abandoned":
        return state
    asked = stage(state)
    given = {
        name: value
        for name, value in extraction
        if name in ScreeningFields.model_fields and value is not None
    }
    # corrections overwrite, then the rules re-run on the result
    fields = state.fields.model_copy(update=given)
    start = fields.start_date
    if start is not None and not today <= start <= today + START_WINDOW:
        fields = fields.model_copy(update={"start_date": None})
    uncovered = extraction.zone is not None and resolve_zone(extraction.zone) is None
    invalid_answers = dict(state.invalid_answers)
    # an uncovered city is a valid answer with its own re-ask, not an invalid one
    if (
        extraction.intent == "answer"
        and asked in FIELD_STAGES
        and missing(fields, asked)
        and not uncovered
    ):
        invalid_answers[asked] = invalid_answers.get(asked, 0) + 1
    corrected: list[Stage] = [
        s
        for s, name in FIELD_STAGES.items()
        if s in state.corrected
        or (
            name in given
            and not missing(state.fields, s)
            and getattr(fields, name) != getattr(state.fields, name)
        )
    ]
    question: list[Question] = (
        [] if extraction.question is None else [extraction.question]
    )
    return Screening(
        last_message_at=now,
        fields=fields,
        started=state.started or extraction.intent == "answer",
        # a message that changes a field gets the recap again
        confirmed=asked == "confirm"
        and extraction.confirmed is True
        and fields == state.fields,
        withdrawn=extraction.intent == "withdraw",
        abusive_messages=state.abusive_messages + (extraction.intent == "abusive"),
        uncovered_zones=state.uncovered_zones + uncovered,
        invalid_answers=invalid_answers,
        corrected=corrected,
        topics=[*state.topics, *question],
    )
