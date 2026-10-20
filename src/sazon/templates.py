"""Text that code sends word for word, never phrased by the LLM: the greeting,
closings and approved answers as (Spanish, English) pairs (decisions 006, 011,
018-020), and the key data shown in the recap and the summary (013).
"""

from sazon import engine
from sazon.engine import ZONES, Outcome, Reason, Screening, resolve_zone
from sazon.schema import Language, Question, ScreeningFields

PRIVACY = "https://gruposazon.example/privacidad"  # fictional client

GREETING = (
    "¡Hola! Soy Leo, el asistente virtual (una IA) de Grupo Sazón. Te haré unas"
    " preguntas sobre tu solicitud de repartidor: unos 2 minutos. Privacidad:"
    f" {PRIVACY}. ¿Empezamos?"
)
# Any other language gets a Spanish reply offering Spanish or English.
OTHER_LANGUAGE = (
    "Perdona, solo puedo atenderte en español o en inglés (Spanish or English)."
    " ¿En cuál seguimos?"
)
SAY_AGAIN = (
    "Perdona, no te entendí bien. ¿Me lo repites?",
    "Sorry, I didn't get that. Could you say it again?",
)
WARNING = (
    "Mantengamos el respeto, por favor: otro mensaje así cerrará la conversación.",
    "Let's keep it respectful, please: another message like that ends the chat.",
)
ANSWERS: dict[Question, tuple[str, str]] = {
    "duration": (
        "Son unas pocas preguntas, unos 2 minutos.",
        "It's just a few questions, about 2 minutes.",
    ),
    "next_steps": (
        "Al terminar, un reclutador revisa tus respuestas y, si cumples los"
        " requisitos, te escribe por aquí.",
        "When we finish, a recruiter reviews your answers and, if you meet the"
        " requirements, messages you here.",
    ),
    "data_use": (
        f"Usamos tus respuestas solo para valorar tu solicitud. Más info: {PRIVACY}",
        f"We use your answers only to assess your application. More: {PRIVACY}",
    ),
    "other": (
        "Eso te lo confirmará un reclutador.",
        "A recruiter will confirm that.",
    ),
}
CLOSINGS: dict[tuple[Outcome, Reason | None], tuple[str, str]] = {
    ("qualified", None): (
        "¡Listo, gracias! Un reclutador te escribirá por aquí. 🙌",
        "All done, thanks! A recruiter will message you here. 🙌",
    ),
    ("needs_review", None): (
        "¡Gracias! Una persona revisará tu solicitud.",
        "Thanks! A person will review your application.",
    ),
    ("disqualified", "no_license"): (
        "Gracias por tu interés. Para este puesto hace falta carné o licencia de"
        " conducir, así que no podemos seguir. Si es un error, dínoslo aquí.",
        "Thanks for your interest. This role needs a driving licence, so we can't"
        " go ahead. If this is a mistake, tell us here.",
    ),
    ("disqualified", "zone_not_covered"): (
        "Gracias por tu interés. De momento no repartimos en tu ciudad, así que no"
        " podemos seguir. Si es un error, dínoslo aquí. ¿Quieres que te avisemos"
        " si abrimos en tu ciudad?",
        "Thanks for your interest. We don't deliver in your city yet, so we can't"
        " go ahead. If this is a mistake, tell us here. Shall we let you know if"
        " we open in your city?",
    ),
    ("withdrawn", None): (
        "Gracias por tu tiempo. Aquí estaremos si cambias de opinión.",
        "Thanks for your time. We're here if you change your mind.",
    ),
    ("withdrawn", "abusive"): (
        "Vamos a cerrar la conversación aquí.",
        "We're closing the conversation here.",
    ),
}
POOL_YES = (
    "¡Hecho! Te avisaremos si abrimos en tu ciudad.",
    "Done! We'll let you know if we open in your city.",
)
POOL_NO = ("Entendido. ¡Gracias por tu tiempo!", "Got it. Thanks for your time!")
AFTER_CLOSE = (
    "Gracias, una persona revisará tu mensaje.",
    "Thanks, a person will review your message.",
)


def say(text: tuple[str, str], language: Language) -> str:
    """Spanish unless the conversation is in English."""
    spanish, english = text
    return english if language == "en" else spanish


NOT_GIVEN = "not given"


def key_data(fields: ScreeningFields) -> str:
    """The validated fields as text, in English: the LLM shows them back at
    CONFIRM, and the summary starts with them."""
    zone = NOT_GIVEN
    if fields.zone is not None:
        city = resolve_zone(fields.zone)
        covered = f"{city} ({ZONES[city].country})" if city else "not covered"
        zone = f"{fields.zone} → {covered}"
    experience = NOT_GIVEN
    if (e := fields.prior_delivery_experience) is not None:
        platforms = ", ".join(e.platforms) + (
            f" ({e.other_platform})" if e.other_platform else ""
        )
        experience = f"{e.years:g} years" + (f" on {platforms}" if platforms else "")
    licence = {True: "yes", False: "no", None: NOT_GIVEN}[fields.has_license]
    return "\n".join(
        [
            f"Full name: {fields.full_name or NOT_GIVEN}",
            f"Driving licence: {licence}",
            f"Zone: {zone}",
            f"Availability: {fields.availability or NOT_GIVEN}",
            f"Preferred schedule: {fields.preferred_schedule or NOT_GIVEN}",
            f"Delivery experience: {experience}",
            f"Start date: {fields.start_date or NOT_GIVEN}",
        ]
    )


def summary(
    state: Screening, outcome: Outcome, reason: Reason | None, notes: list[str]
) -> str:
    """Key data rendered by code, then the LLM's notes, labelled (decision 013)."""
    return "\n".join(
        [
            f"Outcome: {outcome}" + (f" ({reason})" if reason else ""),
            key_data(state.fields),
            f"Flagged fields: {', '.join(engine.flagged(state)) or 'none'}",
            "",
            "AI-generated notes:",
            *(f"- {note}" for note in notes or ["unavailable"]),
        ]
    )
