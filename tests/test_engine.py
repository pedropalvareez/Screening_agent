from datetime import UTC, datetime, timedelta

import pytest

from sazon.engine import Screening, apply, flagged, outcome, stage
from sazon.schema import Extraction, Intent

NOW = datetime(2026, 10, 19, 12, tzinfo=UTC)
TODAY = NOW.date()
FRESH = Screening(last_message_at=NOW)


def msg(intent: Intent = "answer", **fields: object) -> Extraction:
    return Extraction.model_validate({"intent": intent, "language": "es", **fields})


def run(state: Screening, *messages: Extraction) -> Screening:
    for message in messages:
        state = apply(state, message, NOW, TODAY)
    return state


# One valid answer per field stage, in asking order.
ANSWERS = [
    msg(has_license=True),
    msg(zone="Madrid"),
    msg(full_name="Ana López"),
    msg(availability="part_time"),
    msg(preferred_schedule="evening"),
    msg(prior_delivery_experience={"years": 2, "platforms": ["glovo"]}),
    msg(start_date=TODAY),
]
BEFORE_START = run(FRESH, msg(), *ANSWERS[:-1])
AT_CONFIRM = run(BEFORE_START, ANSWERS[-1])


def test_stage_follows_the_fixed_order() -> None:
    state = FRESH
    stages = [stage(state)]
    for message in [msg(), *ANSWERS]:
        state = apply(state, message, NOW, TODAY)
        stages.append(stage(state))
    assert stages == [
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


def test_greeting_waits_for_an_answer() -> None:
    assert stage(run(FRESH, msg("question"))) == "greeting"


def test_one_message_fills_several_fields_in_any_order() -> None:
    state = run(FRESH, msg(has_license=True, zone="Madrid", start_date=TODAY))
    assert stage(state) == "name"
    assert state.fields.start_date == TODAY


def test_zero_years_needs_no_platforms() -> None:
    experience = msg(prior_delivery_experience={"years": 0})
    state = run(FRESH, msg(), *ANSWERS[:5], experience)
    assert stage(state) == "start_date"


def test_no_license_disqualifies_and_closes() -> None:
    state = run(FRESH, msg(), msg(has_license=False))
    assert outcome(state, NOW) == ("disqualified", "no_license")
    assert run(state, msg(has_license=True)) == state


@pytest.mark.parametrize("days", [0, 365])
def test_start_date_inside_window_is_kept(days: int) -> None:
    start = TODAY + timedelta(days=days)
    state = run(BEFORE_START, msg(start_date=start))
    assert state.fields.start_date == start
    assert stage(state) == "confirm"


@pytest.mark.parametrize("days", [-1, 366])
def test_start_date_outside_window_is_an_invalid_answer(days: int) -> None:
    invalid = msg(start_date=TODAY + timedelta(days=days))
    state = run(BEFORE_START, invalid)
    assert state.fields.start_date is None
    assert stage(state) == "start_date"
    assert flagged(run(state, invalid, invalid)) == ["start_date"]


def test_third_invalid_answer_flags_the_field_and_moves_on() -> None:
    twice = run(FRESH, msg(), msg(), msg())
    assert stage(twice) == "license"
    thrice = run(twice, msg())
    assert flagged(thrice) == ["license"]
    assert stage(thrice) == "zone"
    assert outcome(thrice, NOW) is None  # ambiguity never disqualifies
    done = run(thrice, *ANSWERS[1:], msg(confirmed=True))
    assert outcome(done, NOW) == ("needs_review", None)


@pytest.mark.parametrize("intent", ["question", "off_topic"])
def test_only_answers_count_as_invalid(intent: Intent) -> None:
    state = run(FRESH, msg(), msg(intent), msg(intent), msg(intent))
    assert stage(state) == "license"
    assert flagged(state) == []


def test_confirming_the_recap_qualifies() -> None:
    assert outcome(run(AT_CONFIRM, msg(confirmed=True)), NOW) == ("qualified", None)


@pytest.mark.parametrize(
    "state",
    [run(FRESH, msg(confirmed=True), *ANSWERS), run(AT_CONFIRM, msg(confirmed=False))],
    ids=["confirmed before confirm", "recap rejected"],
)
def test_screening_stays_open_without_a_confirmed_recap(state: Screening) -> None:
    assert stage(state) == "confirm"
    assert outcome(state, NOW) is None


def test_correction_overwrites_and_shows_the_recap_again() -> None:
    state = run(AT_CONFIRM, msg(zone="Barcelona", confirmed=True))
    assert state.fields.zone == "Barcelona"
    assert stage(state) == "confirm"
    assert outcome(state, NOW) is None


def test_correction_reruns_the_rules() -> None:
    no_license = run(AT_CONFIRM, msg(has_license=False))
    assert outcome(no_license, NOW) == ("disqualified", "no_license")
    past_date = run(AT_CONFIRM, msg(start_date=TODAY - timedelta(days=1)))
    assert stage(past_date) == "start_date"


def test_correcting_a_flagged_field_clears_the_flag() -> None:
    flagged_license = run(FRESH, msg(), msg(), msg(), msg(), *ANSWERS[1:])
    state = run(flagged_license, msg(has_license=True), msg(confirmed=True))
    assert outcome(state, NOW) == ("qualified", None)


@pytest.mark.parametrize("state", [FRESH, AT_CONFIRM], ids=["greeting", "confirm"])
def test_withdraw_closes_from_any_stage(state: Screening) -> None:
    assert outcome(run(state, msg("withdraw")), NOW) == ("withdrawn", None)


def test_second_abusive_message_withdraws() -> None:
    warned = run(FRESH, msg(), msg("abusive"))
    assert outcome(warned, NOW) is None
    assert outcome(run(warned, msg("abusive")), NOW) == ("withdrawn", "abusive")


def test_abandoned_after_72_hours_without_a_candidate_message() -> None:
    state = run(FRESH, msg())
    deadline = NOW + timedelta(hours=72)
    assert outcome(state, deadline - timedelta(seconds=1)) is None
    assert outcome(state, deadline) == ("abandoned", None)


def test_abandoned_candidate_who_returns_resumes() -> None:
    later = NOW + timedelta(hours=100)
    state = apply(run(FRESH, msg()), msg(has_license=True), later, later.date())
    assert outcome(state, later) is None
    assert stage(state) == "zone"


def test_silence_does_not_replace_a_closed_outcome() -> None:
    state = run(FRESH, msg(), msg(has_license=False))
    later = NOW + timedelta(days=30)
    assert outcome(state, later) == ("disqualified", "no_license")
