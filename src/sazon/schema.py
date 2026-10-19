"""Screening fields and LLM extraction output.

Format only: business rules (start-date window, zone coverage) live in engine.py.
"""

from datetime import date
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Availability = Literal["full_time", "part_time", "weekends"]
Schedule = Literal["morning", "afternoon", "evening", "flexible"]
Platform = Literal[
    "glovo", "uber_eats", "just_eat", "rappi", "didi_food", "own_fleet", "other"
]
Intent = Literal["answer", "question", "withdraw", "off_topic", "abusive"]
Language = Literal["es", "en", "other"]

FullName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=2, max_length=100, pattern=r"^\S+(\s+\S+)+$"
    ),
]
RawText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]


class Strict(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class PriorDeliveryExperience(Strict):
    years: float = Field(ge=0, le=50)
    platforms: list[Platform] = []
    other_platform: RawText | None = None

    @model_validator(mode="after")
    def platforms_match_years(self) -> Self:
        if (self.years > 0) != bool(self.platforms):
            raise ValueError("platforms are required when years > 0, else empty")
        if ("other" in self.platforms) != (self.other_platform is not None):
            raise ValueError("other_platform is required exactly when other is listed")
        return self


class ScreeningFields(Strict):
    """Every field optional: a screening fills them over several turns."""

    full_name: FullName | None = None
    has_license: bool | None = None
    zone: RawText | None = None  # as written; engine.py resolves the city
    availability: Availability | None = None
    preferred_schedule: Schedule | None = None
    prior_delivery_experience: PriorDeliveryExperience | None = None
    start_date: date | None = None


class Extraction(ScreeningFields):
    """One LLM extraction: fields present in the message, plus intent and language."""

    intent: Intent
    language: Language
