"""Minimal analytics (decision 023), from the stored conversations and engine.py's
rules. Pure, like engine.py: callers pass `now`.

Each metric counts the screening's outcome: a reopened DISQUALIFIED stays
DISQUALIFIED, as 017's guardrail needs. Conversations still screening count
nowhere.
"""

import statistics
from collections import Counter
from datetime import datetime, timedelta
from typing import get_args

from sazon import engine
from sazon.engine import Stage
from sazon.schema import Language, Strict
from sazon.storage import Conversation

# 80% of recruiter time goes to unqualified candidates (brief), so each qualified
# costs 1 / (1 - 0.8) calls of recruiter time today (017).
BASELINE_CALLS = 5
# [assumption] an 8-hour day over the brief's ~15 calls a day (017).
MINUTES_PER_CALL = 8 * 60 / 15


class Rate(Strict):
    count: int
    total: int


class Metrics(Strict):
    completed: Rate  # decided, of the candidates who replied
    dropped_off: dict[Stage, int]  # withdrawn or abandoned, by the pending question
    median_minutes: float | None  # first candidate message to the close, Q and NR
    needs_review: Rate  # of QUALIFIED + NEEDS_REVIEW
    flagged: dict[str, Rate]  # by field name, as in the JSON, of Q + NR
    by_language: dict[Language, Rate]  # the conversation's last language (021)
    reopened: Rate  # of DISQUALIFIED
    pool: Rate  # opt-ins, of DISQUALIFIED for zone_not_covered (018)
    showed_up: Rate  # of showed_up + no_show (017)
    minutes_per_qualified: float | None  # Q + NR + reopened calls per qualified
    baseline_minutes: float
    minutes_per_call: float


def measure(conversations: list[Conversation], now: datetime) -> Metrics:
    closed = [(c, c.closing) for c in conversations if c.closing is not None]
    queue = [(c, k) for c, k in closed if k.outcome in ("qualified", "needs_review")]
    review = [(c, k) for c, k in queue if k.outcome == "needs_review"]
    disqualified = [c for c, k in closed if k.outcome == "disqualified"]
    zone = [c for c, k in closed if k.reason == "zone_not_covered"]
    reopened = sum(c.reopened_at is not None for c in disqualified)
    qualified = len(queue) - len(review)
    # left after replying: those who never replied are 017's response rate
    dropped = [c for c, k in closed if k.outcome == "withdrawn"] + [
        c
        for c in conversations
        if c.closing is None
        and engine.outcome(c.screening, now) == ("abandoned", None)
        and any(line.role == "candidate" for line in c.transcript)
    ]
    left_at = Counter(engine.stage(c.screening) for c in dropped)
    decided = len(queue) + len(disqualified)
    minutes = [
        (k.at - next(line.at for line in c.transcript if line.role == "candidate"))
        / timedelta(minutes=1)
        for c, k in queue
    ]
    statuses = Counter(c.recruiter_status for c in conversations)
    return Metrics(
        completed=Rate(count=decided, total=decided + len(dropped)),
        dropped_off={s: left_at[s] for s in get_args(Stage) if left_at[s]},
        median_minutes=statistics.median(minutes) if minutes else None,
        needs_review=Rate(count=len(review), total=len(queue)),
        flagged={
            engine.FIELD_STAGES[s]: Rate(
                count=sum(s in k.flagged for _, k in review), total=len(queue)
            )
            for s in engine.FIELD_STAGES
            if any(s in k.flagged for _, k in review)
        },
        by_language={
            language: Rate(
                count=sum(c.language == language for c, _ in review),
                total=sum(c.language == language for c, _ in queue),
            )
            for language in get_args(Language)
            if any(c.language == language for c, _ in queue)
        },
        reopened=Rate(count=reopened, total=len(disqualified)),
        pool=Rate(count=sum(c.pool is not None for c in zone), total=len(zone)),
        showed_up=Rate(
            count=statuses["showed_up"],
            total=statuses["showed_up"] + statuses["no_show"],
        ),
        minutes_per_qualified=(len(queue) + reopened) / qualified * MINUTES_PER_CALL
        if qualified
        else None,
        baseline_minutes=BASELINE_CALLS * MINUTES_PER_CALL,
        minutes_per_call=MINUTES_PER_CALL,
    )
