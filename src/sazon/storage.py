"""SQLite storage: one row per conversation, holding the whole record as JSON.

Every read validates the record. Each call opens its own connection: FastAPI runs
requests on several threads, and a sqlite3 connection must stay on one.
"""

import contextlib
import sqlite3
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, Field

from sazon.engine import Outcome, Reason, Screening, Stage
from sazon.schema import Language, RawText, Strict


class Line(Strict):
    at: AwareDatetime
    role: Literal["candidate", "agent"]
    text: str  # redacted before it gets here


class Closing(Strict):
    """Set once, when the screening reaches a terminal state."""

    at: AwareDatetime
    outcome: Outcome
    reason: Reason | None
    flagged: list[Stage]
    summary: str


class PoolConsent(Strict):
    """A yes to "shall we tell you if we open in your city?" (decision 018)."""

    at: AwareDatetime
    expires_on: date
    city: RawText  # as written


class Conversation(Strict):
    id: str
    created_at: AwareDatetime
    language: Language  # es or en: a message in another language never changes it
    screening: Screening
    transcript: list[Line]
    # job questions, logged for the recruiter (019)
    questions: list[str] = Field(default_factory=list[str])
    closing: Closing | None = None
    wrote_after_close: bool = False  # flagged for human review
    pool: PoolConsent | None = None


def create(db: Path) -> None:
    """Create the table if missing; run at startup, so a bad path fails there."""
    with contextlib.closing(sqlite3.connect(db)) as connection, connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS conversations"
            " (id TEXT PRIMARY KEY, record TEXT NOT NULL)"
        )


def save(db: Path, conversation: Conversation) -> None:
    with contextlib.closing(sqlite3.connect(db)) as connection, connection:
        connection.execute(
            "INSERT OR REPLACE INTO conversations (id, record) VALUES (?, ?)",
            (conversation.id, conversation.model_dump_json()),
        )


def load(db: Path, conversation_id: str) -> Conversation | None:
    with contextlib.closing(sqlite3.connect(db)) as connection:
        row = connection.execute(
            "SELECT record FROM conversations WHERE id = ?", (conversation_id,)
        ).fetchone()
    return None if row is None else Conversation.model_validate_json(row[0])
