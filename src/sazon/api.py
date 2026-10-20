"""HTTP entry points. The LLM is reached only through turn.py."""

import functools
import os
import secrets
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal, get_args

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import AwareDatetime, StringConstraints

from sazon import engine, storage, templates
from sazon.engine import ZONES, Outcome, Reason, RecruiterStatus, Stage
from sazon.schema import Language, ScreeningFields, Strict
from sazon.storage import Conversation, Line, PoolConsent
from sazon.turn import (
    Agent,
    Reply,
    UnknownConversation,
    connect,
    latest_reply,
    lock,
    start,
    turn,
)

WEB = Path(__file__).parent / "web"


@functools.cache
def get_agent() -> Agent:
    return connect()


def panel_credentials() -> tuple[str, str]:
    """The recruiters' shared login (decision 012), read on every request."""
    user = os.environ.get("PANEL_USER")
    password = os.environ.get("PANEL_PASSWORD")
    # Blank fails too: a copied .env.example has no values. FastAPI decodes Basic
    # auth as ASCII, so any other character could never log in.
    if not user or not password or not (user + password).isascii():
        raise RuntimeError(
            "PANEL_USER and PANEL_PASSWORD must be set, in ASCII: fill them in .env"
            " and pass --env-file .env to uv run or docker run"
        )
    return user, password


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
    get_agent()  # fail at startup, not on the first candidate
    panel_credentials()  # or on the first recruiter
    yield


app = FastAPI(title="Grupo Sazón screening", lifespan=lifespan)
AgentDep = Annotated[Agent, Depends(get_agent)]


def recruiter(
    credentials: Annotated[HTTPBasicCredentials, Depends(HTTPBasic())],
) -> None:
    user, password = panel_credentials()
    # Both compared, in constant time, so timing reveals neither.
    right_user = secrets.compare_digest(credentials.username, user)
    right_password = secrets.compare_digest(credentials.password, password)
    if not (right_user and right_password):
        raise HTTPException(401, "wrong credentials", {"WWW-Authenticate": "Basic"})


def json_only(request: Request) -> None:
    """Writes take JSON only. The browser resends Basic auth on a post from any
    site, but without a CORS preflight, which this app never approves, a
    cross-site page can only send a form, text or no Content-Type (CSRF). FastAPI
    refuses those for a JSON body; reopen has none, so this check is its guard."""
    if not request.headers.get("content-type", "").startswith("application/json"):
        raise HTTPException(415, "send application/json")


# Every panel route sits on this router, so none can miss the login.
panel = APIRouter(prefix="/panel", dependencies=[Depends(recruiter)])


class CandidateMessage(Strict):
    text: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)
    ]


class Started(Strict):
    id: str
    reply: Reply


class Resumed(Strict):
    """The chat after a reload: the transcript, then the last reply's options."""

    transcript: list[Line]
    reply: Reply


class Candidate(Strict):
    """One row of the recruiter's lists."""

    id: str
    outcome: Outcome  # NEEDS_REVIEW once reopened
    reason: Reason | None
    at: AwareDatetime  # closed, or the last message while ABANDONED
    stopped: Stage | None  # where an ABANDONED candidate stopped
    name: str | None
    zone: str | None  # as written
    city: str | None  # the service city it resolves to, None if not covered
    country: str | None
    flagged: list[str]  # field names, as in the JSON
    status: RecruiterStatus
    reopened_at: AwareDatetime | None
    wrote_after_close: bool  # needs a human (process-design §2)


class CandidateDetail(Strict):
    candidate: Candidate
    summary: str  # rendered by code from the fields
    notes: list[str]  # AI-generated (decision 013)
    fields: ScreeningFields
    questions: list[str]  # job questions for a recruiter (019)
    pool: PoolConsent | None  # 018
    language: Language
    transcript: list[Line]


class StatusChange(Strict):
    status: RecruiterStatus


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/conversations")
def open_conversation(agent: AgentDep) -> Started:
    conversation_id, reply = start(agent, datetime.now(UTC))
    return Started(id=conversation_id, reply=reply)


@app.get("/conversations/{conversation_id}")
def resume(conversation_id: str, agent: AgentDep) -> Resumed:
    conversation = storage.load(agent.db, conversation_id)
    if conversation is None:
        raise HTTPException(404, "conversation not found")
    return Resumed(transcript=conversation.transcript, reply=latest_reply(conversation))


@app.post("/conversations/{conversation_id}/messages")
def send_message(
    conversation_id: str, message: CandidateMessage, agent: AgentDep
) -> Reply:
    try:
        return turn(agent, conversation_id, message.text, datetime.now(UTC))
    except UnknownConversation:
        raise HTTPException(404, "conversation not found") from None


def outcome(c: Conversation, now: datetime) -> Outcome | None:
    """What the panel shows: the closing's outcome, NEEDS_REVIEW once reopened,
    ABANDONED (computed on read, never stored), or None while still screening."""
    if c.closing is None:
        result = engine.outcome(c.screening, now)
        return None if result is None else result[0]
    return engine.reopened(c.closing.outcome) if c.reopened_at else c.closing.outcome


def candidate(c: Conversation, shown: Outcome) -> Candidate:
    fields = c.screening.fields
    city = None if fields.zone is None else engine.resolve_zone(fields.zone)
    flagged = engine.flagged(c.screening) if c.closing is None else c.closing.flagged
    return Candidate(
        id=c.id,
        outcome=shown,
        reason=None if c.closing is None else c.closing.reason,
        at=c.screening.last_message_at if c.closing is None else c.closing.at,
        stopped=engine.stage(c.screening) if shown == "abandoned" else None,
        name=fields.full_name,
        zone=fields.zone,
        city=city,
        country=None if city is None else ZONES[city].country,
        flagged=[engine.FIELD_STAGES[stage] for stage in flagged],
        status=c.recruiter_status,
        reopened_at=c.reopened_at,
        wrote_after_close=c.wrote_after_close,
    )


def detail(c: Conversation, shown: Outcome) -> CandidateDetail:
    """ABANDONED has no closing: its summary is the key data, with no AI notes."""
    return CandidateDetail(
        candidate=candidate(c, shown),
        summary=templates.key_data(c.screening.fields)
        if c.closing is None
        else c.closing.summary,
        notes=[] if c.closing is None else c.closing.notes,
        fields=c.screening.fields,
        questions=c.questions,
        pool=c.pool,
        language=c.language,
        transcript=c.transcript,
    )


def screened(agent: Agent, conversation_id: str) -> tuple[Conversation, Outcome]:
    """A conversation the panel shows: one still screening is not found."""
    c = storage.load(agent.db, conversation_id)
    shown = None if c is None else outcome(c, datetime.now(UTC))
    if c is None or shown is None:
        raise HTTPException(404, "candidate not found")
    return c, shown


@panel.get("")
def panel_page() -> FileResponse:
    # No other site may frame the panel (clickjacking on reopen), and only our
    # own files run in it, should candidate text ever slip into the page as HTML.
    csp = "default-src 'self'; frame-ancestors 'none'"
    return FileResponse(
        WEB / "panel" / "index.html", headers={"Content-Security-Policy": csp}
    )


@panel.get("/candidates")
def candidates(agent: AgentDep) -> list[Candidate]:
    """QUALIFIED first, then NEEDS_REVIEW (process-design §6), each oldest first."""
    now = datetime.now(UTC)
    rows = [
        candidate(c, shown)
        for c in storage.load_all(agent.db)
        if (shown := outcome(c, now)) is not None
    ]
    return sorted(rows, key=lambda row: (get_args(Outcome).index(row.outcome), row.at))


@panel.get("/candidates/{conversation_id}")
def candidate_detail(conversation_id: str, agent: AgentDep) -> CandidateDetail:
    return detail(*screened(agent, conversation_id))


@panel.post("/candidates/{conversation_id}/status", dependencies=[Depends(json_only)])
def set_status(
    conversation_id: str, change: StatusChange, agent: AgentDep
) -> CandidateDetail:
    with lock(conversation_id):  # a turn saving meanwhile would undo the change
        c, shown = screened(agent, conversation_id)
        c.recruiter_status = change.status
        storage.save(agent.db, c)
    return detail(c, shown)


@panel.post("/candidates/{conversation_id}/reopen", dependencies=[Depends(json_only)])
def reopen(conversation_id: str, agent: AgentDep) -> CandidateDetail:
    with lock(conversation_id):
        c, shown = screened(agent, conversation_id)
        try:
            shown = engine.reopened(shown)
        except ValueError as error:
            raise HTTPException(409, str(error)) from None
        c.reopened_at = datetime.now(UTC)
        storage.save(agent.db, c)
    return detail(c, shown)


# Last among the panel routes: "candidates" would match {asset} too.
@panel.get("/{asset}")
def panel_asset(asset: Literal["panel.js", "panel.css"]) -> FileResponse:
    return FileResponse(WEB / "panel" / asset)


app.include_router(panel)
# Last, so the routes above match first. The id travels in the URL fragment,
# which the browser never sends to the server. The panel lives outside this
# folder: anything inside it is public.
app.mount("/", StaticFiles(directory=WEB / "chat", html=True))
