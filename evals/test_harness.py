"""The eval harness without the network: naming(), percentile(), comparable() and
metrics() on made-up runs, so the reported numbers are tested in CI. Every name
is fictional."""

from test_conversations import (
    ES,
    Call,
    Exchange,
    Experience,
    NotesVerdict,
    ReplyVerdict,
    Run,
    comparable,
    metrics,
    naming,
    percentile,
)

from sazon.schema import Extraction

REPLY = "¡Hola! ¿Dónde vives?"


def call(reply: str | None) -> Call:
    """An extraction call; None when it failed."""
    return Call(kind="extraction", seconds=1.0, prompt="", reply=reply)


def exchange(
    message: str,
    expected: Extraction,
    got: Extraction | None,
    calls: list[Call],
    verdict: ReplyVerdict | None = None,
) -> Exchange:
    return Exchange(
        message=message,
        expected=expected,
        got=got,
        reply=REPLY,
        language="es",
        worded=None if verdict is None else REPLY,
        directive=None,
        recap=False,
        seconds=1.0,
        calls=calls,
        verdict=verdict,
    )


def test_naming_finds_names_and_gendered_pronouns() -> None:
    notes = ["Lucía asked about pay.", "She corrected her city."]
    assert naming(notes, "Lucía Pérez Gómez") == ["Lucía", "She", "her"]


def test_naming_skips_pronouns_in_quotes() -> None:
    notes = ['The candidate wrote "ya te lo he dicho" and “he dicho Getafe”.']
    assert naming(notes, "Lucía Pérez Gómez") == []


def test_percentile_takes_the_nearest_rank() -> None:
    values = [4.0, 1.0, 3.0, 2.0]
    assert percentile(values, 0.5) == 2.0  # a value in the list, not 2.5
    assert percentile(values, 0.95) == 4.0


def test_comparable_ignores_platform_order() -> None:
    one = Experience(years=3, platforms=["rappi", "didi_food"])
    other = Experience(years=3, platforms=["didi_food", "rappi"])
    assert one != other
    assert comparable(one) == comparable(other)


def test_metrics_counts_and_lists_failures() -> None:
    confirmed = ES(has_license=True, confirmed=True)  # confirmed where none was asked
    madrid = ES(zone="Madrid")
    run = Run(
        label="happy_es #0",
        scripted="qualified",
        outcome="needs_review",
        exchanges=[
            exchange(
                "Sí, tengo carné",
                ES(has_license=True),
                confirmed,
                [call("{"), call(confirmed.model_dump_json())],
                ReplyVerdict(
                    language="es",
                    promises=False,
                    greets=True,
                    thanks_bad_news=False,
                    contradicts=False,
                    judges=False,
                ),
            ),
            exchange(
                "Vivo en Getafe",
                ES(zone="Getafe"),
                madrid,
                [call(madrid.model_dump_json())],
            ),
            exchange("Lucía", ES(), None, [call(None)]),
        ],
        notes=["The candidate seems motivated."],
        named=[],
        notes_verdict=NotesVerdict(language="en", assesses=True, unsupported=False),
    )

    report = metrics([run])

    assert (
        "Turns: 3. Extraction replies that are invalid JSON (they get the retry):"
        " 1/3 (33%). Failed calls: 1"
    ) in report
    assert "  confirmed set elsewhere, which the engine ignores: 1" in report
    assert report[report.index("Failures: 5") :] == [
        "Failures: 5",
        "  happy_es #0: ended needs_review, scripted qualified",
        f"  happy_es #0 turn 1: greets: {REPLY!r}",
        "  happy_es #0 turn 2: zone 'Madrid', expected 'Getafe' from 'Vivo en Getafe'",
        "  happy_es #0 turn 3: no usable extraction of 'Lucía'",
        "  happy_es #0 notes: assesses the candidate:"
        " ['The candidate seems motivated.']",
    ]
