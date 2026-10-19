import json
from datetime import date

import pytest
from pydantic import ValidationError

from sazon.schema import Extraction

VALID: dict[str, object] = {
    "full_name": "Ana López García",
    "has_license": True,
    "zone": "Getafe",
    "availability": "part_time",
    "preferred_schedule": "evening",
    "prior_delivery_experience": {
        "years": 1.5,
        "platforms": ["glovo", "other"],
        "other_platform": "Stuart",
    },
    "start_date": "2026-11-02",
    "intent": "answer",
    "language": "es",
}


def parse(**changes: object) -> Extraction:
    """Validate VALID with changes applied, as JSON, the way LLM output arrives."""
    return Extraction.model_validate_json(json.dumps(VALID | changes))


def experience(**changes: object) -> dict[str, object]:
    return {"years": 2, "platforms": ["rappi"]} | changes


def test_valid_extraction_parses() -> None:
    extraction = parse()
    assert extraction.start_date == date(2026, 11, 2)
    assert extraction.prior_delivery_experience is not None
    assert extraction.prior_delivery_experience.platforms == ["glovo", "other"]


def test_only_intent_and_language_are_required() -> None:
    minimal = '{"intent": "question", "language": "en"}'
    extraction = Extraction.model_validate_json(minimal)
    assert extraction.full_name is None


def test_zero_years_needs_no_platforms() -> None:
    parsed = parse(prior_delivery_experience={"years": 0}).prior_delivery_experience
    assert parsed is not None
    assert parsed.platforms == []


@pytest.mark.parametrize(
    "changes",
    [
        pytest.param({"full_name": "Ana"}, id="one-word name"),
        pytest.param({"full_name": "A " * 51}, id="name over 100 chars"),
        pytest.param(
            {"prior_delivery_experience": experience(years=51)}, id="years 51"
        ),
        pytest.param(
            {"prior_delivery_experience": experience(platforms=[])},
            id="platforms missing with years > 0",
        ),
        pytest.param(
            {"prior_delivery_experience": experience(platforms=["other"])},
            id="other without raw text",
        ),
        pytest.param(
            {"prior_delivery_experience": experience(other_platform="Stuart")},
            id="raw text without other",
        ),
        pytest.param({"availability": "sometimes"}, id="unknown enum value"),
        pytest.param({"has_license": "yes"}, id="non-bool licence"),
        pytest.param({"intent": None}, id="null intent"),
        pytest.param({"salary": 1200}, id="extra key"),
        pytest.param(
            {"prior_delivery_experience": experience(vehicle="bike")},
            id="extra key in submodel",
        ),
    ],
)
def test_invalid_extraction_is_rejected(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        parse(**changes)
