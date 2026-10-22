"""A week of fictional applications for the demo panel and the metrics tests
(decision 023):

    uv run python src/seed.py demo.db

then start the app with DB_PATH=demo.db. Every conversation goes through start()
and turn() with a scripted LLM, so the records hold what the real pipeline writes:
redacted transcripts, the engine's state and the code summary. No network, no
key. It writes only to a file that does not exist yet and never reads DB_PATH, so
it cannot mix fictional candidates into a real database.
"""

import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from sazon import storage
from sazon.engine import RecruiterStatus
from sazon.llm import Message
from sazon.schema import Extraction, Intent, Language
from sazon.storage import Conversation
from sazon.turn import Agent, start, turn

# A candidate message, what the LLM extracts from it, and what it phrases next:
# Leo's next question, or the summary note when the message closes the screening.
# None when the message makes no phrasing call (the talent-pool answer).
Step = tuple[str, Extraction, str | None]


class Script:
    """Implements the LLM protocol: each call returns the next scripted answer."""

    def __init__(self, steps: list[Step]) -> None:
        self.extractions = iter([extraction for _, extraction, _ in steps])
        self.phrases = iter([phrase for _, _, phrase in steps if phrase is not None])

    def extract(self, messages: list[Message]) -> Extraction:
        return next(self.extractions)

    def phrase(self, messages: list[Message]) -> str:
        return next(self.phrases)

    def transcribe(self, audio: bytes, format: str) -> str:
        raise NotImplementedError("the seed types every message")

    def speak(self, text: str, language: Language) -> bytes:
        raise NotImplementedError("the seed types every message")


def said(
    language: Language = "es", intent: Intent = "answer", **fields: object
) -> Extraction:
    return Extraction.model_validate({"intent": intent, "language": language, **fields})


def spanish(name: str, zone: str, start: date) -> list[Step]:
    """A whole screening in Spanish, up to the yes to the recap."""
    experience = {"years": 1, "platforms": ["glovo"]}
    return [
        ("Sí, empecemos", said(), "¿Tienes carné o licencia de conducir?"),
        ("Sí, tengo", said(has_license=True), "¿En qué ciudad vives?"),
        (zone, said(zone=zone), "Anotado. ¿Me dices tu nombre completo?"),
        (
            name,
            said(full_name=name),
            "¿Buscas jornada completa, media jornada o fines de semana?",
        ),
        (
            "Media jornada",
            said(availability="part_time"),
            "¿Prefieres mañanas, tardes, noches o te da igual?",
        ),
        (
            "Por las tardes",
            said(preferred_schedule="afternoon"),
            "¿Has repartido antes? ¿Cuánto tiempo y con qué apps?",
        ),
        (
            "Un año con Glovo",
            said(prior_delivery_experience=experience),
            "¿Desde qué día podrías empezar?",
        ),
        (
            f"Desde el {start:%d/%m}",
            said(start_date=start),
            f"Repaso: {name}, {zone}, desde el {start:%d/%m}. ¿Está todo bien?",
        ),
        ("Sí, todo bien", said(confirmed=True), "NONE"),
    ]


def english(name: str, zone: str, start: date) -> list[Step]:
    """A whole screening in English, up to the yes to the recap."""
    experience = {"years": 2, "platforms": ["uber_eats"]}
    return [
        ("Yes, let's start", said("en"), "Do you have a driving licence?"),
        ("Yes, I do", said("en", has_license=True), "Which city do you live in?"),
        (zone, said("en", zone=zone), "Noted. What's your full name?"),
        (
            name,
            said("en", full_name=name),
            "Are you after full-time, part-time or weekend work?",
        ),
        (
            "Full-time",
            said("en", availability="full_time"),
            "Do you prefer mornings, afternoons, evenings, or are you flexible?",
        ),
        (
            "Evenings",
            said("en", preferred_schedule="evening"),
            "Have you done delivery work before? For how long, and on which apps?",
        ),
        (
            "Two years on Uber Eats",
            said("en", prior_delivery_experience=experience),
            "When could you start?",
        ),
        (
            f"From {start:%d %B}",
            said("en", start_date=start),
            f"Quick recap: {name}, {zone}, starting {start:%d %B}. Is that right?",
        ),
        ("Yes, all correct", said("en", confirmed=True), "NONE"),
    ]


# Three answers with no option in them flag the field (decision 009): the
# availability in Spanish, the preferred schedule in English.
UNSURE_ES: list[Step] = [
    (
        "Depende de la semana",
        said(),
        "Necesito una opción, por ejemplo media jornada. ¿Cuál te encaja?",
    ),
    ("No sé, lo que salga", said(), "¿Jornada completa, media jornada o findes?"),
    ("Ni idea", said(), "Sigamos. ¿Prefieres mañanas, tardes, noches o te da igual?"),
]
UNSURE_EN: list[Step] = [
    (
        "Depends on my other job",
        said("en"),
        "I need one option, for example evenings. Which suits you?",
    ),
    ("Hard to say", said("en"), "Mornings, afternoons, evenings, or flexible?"),
    (
        "Not sure yet",
        said("en"),
        "Let's move on. Have you done delivery work before, and on which apps?",
    ),
]


def not_covered(town: str, pool: bool) -> list[Step]:
    """A town outside the service area, after the licence: one re-ask, then the
    talent-pool question (decision 018)."""
    return [
        (
            town,
            said(zone=town),
            f"Aún no repartimos en {town}. ¿Vives cerca de alguna de estas ciudades?",
        ),
        (f"No, vivo en {town}", said(zone=town), "NONE"),
        ("Sí, avisadme" if pool else "No, gracias", said(confirmed=pool), None),
    ]


def chat(db: Path, at: datetime, gap: timedelta, steps: list[Step]) -> Conversation:
    """One candidate replying every `gap`, through the real turn pipeline."""
    agent = Agent(Script(steps), db)
    conversation_id, _ = start(agent, at)
    for n, (text, _, _) in enumerate(steps, 1):
        turn(agent, conversation_id, text, at + gap * n)
    conversation = storage.load(db, conversation_id)
    assert conversation is not None
    return conversation


def seed(db: Path, now: datetime) -> None:
    """About a week of applications, timed back from now. Every name is fictional."""
    storage.create(db)
    start = now.date() + timedelta(days=7)
    lucia = spanish("Lucía Navarro Gil", "Zaragoza", start)
    tom = english("Tom Herrera Díaz", "Málaga", start)
    cut = spanish("Pablo Díaz Romero", "Madrid", start)  # for chats that stop early
    no_licence: Step = ("No tengo carné", said(has_license=False), "NONE")
    withdraw: Step = ("Mejor lo dejo, gracias", said(intent="withdraw"), "NONE")
    cast: list[tuple[float, int, list[Step], RecruiterStatus]] = [
        # days ago, seconds between messages, messages, recruiter status
        (6.5, 20, spanish("Ana López García", "Getafe", start), "showed_up"),
        (6, 25, spanish("Marta Ruiz Ortega", "Barcelona", start), "showed_up"),
        (5, 30, spanish("Javier Gómez Sanz", "Valencia", start), "no_show"),
        (4, 15, spanish("Luis Hernández Pérez", "CDMX", start), "hired"),
        (2, 40, spanish("Sofía Ramírez Cruz", "Guadalajara", start), "pending"),
        (3, 20, english("Daniel Moreno Vidal", "Madrid", start), "contacted"),
        (1, 35, english("Emma Torres Blanco", "Seville", start), "pending"),
        (3.5, 30, [*lucia[:4], *UNSURE_ES, *lucia[5:]], "pending"),
        (2.5, 30, [*tom[:5], *UNSURE_EN, *tom[6:]], "pending"),
        (0.5, 30, [cut[0], no_licence], "pending"),
        (4.5, 30, [*cut[:2], *not_covered("Toledo", pool=True)], "pending"),
        (2.5, 30, [*cut[:2], *not_covered("Cuenca", pool=True)], "pending"),
        (1.2, 30, [*cut[:2], *not_covered("Oaxaca", pool=False)], "pending"),
        (2, 30, [("No, gracias", said(intent="withdraw"), "NONE")], "pending"),
        (1.5, 30, [*cut[:3], withdraw], "pending"),
        (5, 30, [], "pending"),  # never replied
        (4, 30, cut[:2], "pending"),  # silent at the zone question
        (6, 30, cut[:4], "pending"),  # silent at the availability question
        (1 / 24, 30, cut[:3], "pending"),  # still screening
    ]
    for days, gap, steps, status in cast:
        c = chat(db, now - timedelta(days=days), timedelta(seconds=gap), steps)
        c.recruiter_status = status
        storage.save(db, c)
    # a recruiter reopens a disqualified candidate (decision 012)
    c = chat(db, now - timedelta(days=5.5), timedelta(seconds=30), [cut[0], no_licence])
    c.reopened_at = now - timedelta(days=5)
    storage.save(db, c)


def main(args: list[str]) -> None:
    if len(args) != 1:
        sys.exit("usage: uv run python src/seed.py NEW_FILE")
    db = Path(args[0])
    if db.exists():
        sys.exit(f"{db} exists: the seed writes only to a new file")
    seed(db, datetime.now(UTC))


if __name__ == "__main__":
    main(sys.argv[1:])
