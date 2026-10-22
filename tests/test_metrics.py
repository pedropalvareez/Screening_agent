"""Metrics (decision 023) on the seeded week of fictional conversations."""

from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import seed
from sazon import api, storage
from sazon.metrics import measure
from sazon.storage import Conversation

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def seeded(tmp_path_factory: pytest.TempPathFactory) -> list[Conversation]:
    db = tmp_path_factory.mktemp("seed") / "demo.db"
    seed.seed(db, NOW)
    return storage.load_all(db)


def test_seed_reaches_the_scripted_outcomes(seeded: list[Conversation]) -> None:
    shown = Counter(api.outcome(c, NOW) for c in seeded)
    # one DISQUALIFIED was reopened, so the panel shows it as NEEDS_REVIEW
    assert shown == {
        "qualified": 7,
        "needs_review": 3,
        "disqualified": 4,
        "withdrawn": 2,
        "abandoned": 3,
        None: 1,  # still screening
    }


def test_metrics_on_the_seeded_week(seeded: list[Conversation]) -> None:
    assert measure(seeded, NOW).model_dump() == {
        # 7 qualified + 2 needs review + 5 disqualified, of those 14 plus 2
        # withdrawn and 2 abandoned after a reply; the one who never replied and
        # the one still screening are left out
        "completed": {"count": 14, "total": 18},
        "dropped_off": {"greeting": 1, "zone": 1, "name": 1, "availability": 1},
        # 8 or 10 gaps between messages: 120, 160, 160, 200, 240, 280, 300, 300
        # and 320 seconds
        "median_minutes": 4.0,
        "needs_review": {"count": 2, "total": 9},
        "flagged": {
            "availability": {"count": 1, "total": 9},
            "preferred_schedule": {"count": 1, "total": 9},
        },
        "by_language": {
            "es": {"count": 1, "total": 6},
            "en": {"count": 1, "total": 3},
        },
        "reopened": {"count": 1, "total": 5},
        "pool": {"count": 2, "total": 3},
        "showed_up": {"count": 2, "total": 3},
        # 9 in the queue plus 1 reopened, per 7 qualified, at 32 min a call
        "minutes_per_qualified": pytest.approx(10 / 7 * 32),
        "baseline_minutes": 160,
        "minutes_per_call": 32,
    }


def test_a_silent_screening_counts_once_it_is_abandoned(
    seeded: list[Conversation],
) -> None:
    later = measure(seeded, NOW + timedelta(days=3))
    assert later.completed.model_dump() == {"count": 14, "total": 19}
    assert later.dropped_off["name"] == 2


def test_metrics_with_no_conversations() -> None:
    empty = measure([], NOW)
    assert (empty.completed.total, empty.dropped_off, empty.flagged) == (0, {}, {})
    assert (empty.median_minutes, empty.minutes_per_qualified) == (None, None)


def test_seed_refuses_a_file_that_exists(tmp_path: Path) -> None:
    db = tmp_path / "sazon.db"
    db.write_bytes(b"real conversations")
    with pytest.raises(SystemExit, match="exists"):
        seed.main([str(db)])
    assert db.read_bytes() == b"real conversations"
