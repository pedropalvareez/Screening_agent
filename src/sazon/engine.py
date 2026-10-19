"""Business rules: derived stage, knockouts and outcomes.

Pure functions, no LLM, no I/O and no clock: callers pass `now` and `today`.
"""

from datetime import date, datetime, timedelta
from typing import Literal

from pydantic import AwareDatetime, Field

from sazon.schema import Extraction, ScreeningFields, Strict

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
Reason = Literal["no_license", "abusive"]

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


class Screening(Strict):
    """Conversation state. The stage and outcome are derived from it, never stored."""

    # the candidate's last message; before the first one, when the greeting was sent
    last_message_at: AwareDatetime
    fields: ScreeningFields = ScreeningFields()
    started: bool = False
    confirmed: bool = False
    withdrawn: bool = False
    abusive_messages: int = 0
    invalid_answers: dict[Stage, int] = Field(default_factory=dict[Stage, int])


def flagged(state: Screening) -> list[Stage]:
    """Field stages still empty after MAX_INVALID_ANSWERS invalid answers."""
    return [
        stage
        for stage, field in FIELD_STAGES.items()
        if getattr(state.fields, field) is None
        and state.invalid_answers.get(stage, 0) >= MAX_INVALID_ANSWERS
    ]


def stage(state: Screening) -> Stage:
    """First unmet requirement. A flagged field counts as met, so the screening
    moves on."""
    if not state.started:
        return "greeting"
    skipped = flagged(state)
    for s, field in FIELD_STAGES.items():
        if getattr(state.fields, field) is None and s not in skipped:
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
    if state.confirmed:
        return ("needs_review", None) if flagged(state) else ("qualified", None)
    if now - state.last_message_at >= ABANDON_AFTER:
        return ("abandoned", None)
    return None


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
    invalid_answers = dict(state.invalid_answers)
    field = FIELD_STAGES.get(asked)
    if extraction.intent == "answer" and field and getattr(fields, field) is None:
        invalid_answers[asked] = invalid_answers.get(asked, 0) + 1
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
        invalid_answers=invalid_answers,
    )
