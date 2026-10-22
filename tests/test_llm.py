import base64
import time
from collections.abc import Iterator

import httpx2
import pytest
from pydantic import ValidationError

from sazon.llm import LLM, Message, OpenRouter
from sazon.schema import JSON_OBJECT, Extraction, Language

VALID = '{"has_license": true, "intent": "answer", "language": "es"}'
ASK: list[Message] = [{"role": "user", "content": "Tengo carnet."}]


def completion(content: str) -> httpx2.Response:
    return httpx2.Response(
        200, json={"choices": [{"message": {"role": "assistant", "content": content}}]}
    )


def openrouter(
    monkeypatch: pytest.MonkeyPatch, *replies: httpx2.Response
) -> tuple[LLM, list[httpx2.Request]]:
    """OpenRouter that answers with replies in order and records each request."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "fictional-test-key")
    sent: list[httpx2.Request] = []
    queue = iter(replies)

    def handle(request: httpx2.Request) -> httpx2.Response:
        sent.append(request)
        return next(queue)

    return OpenRouter(httpx2.MockTransport(handle)), sent


def test_missing_or_empty_key_fails_at_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        OpenRouter()
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        OpenRouter()


def test_extract_sends_schema_from_schema_py(monkeypatch: pytest.MonkeyPatch) -> None:
    llm, sent = openrouter(monkeypatch, completion(VALID))
    assert llm.extract(ASK).has_license is True
    expected = Extraction.model_json_schema()
    # The only regex in the schema; providers reject it as too complex.
    del expected["properties"]["full_name"]["anyOf"][0]["pattern"]
    # Every key required, so the model writes each one (null when absent).
    experience = expected["$defs"]["PriorDeliveryExperience"]
    for model in (expected, experience):
        model["required"] = [*model["properties"]]
    body = JSON_OBJECT.validate_json(sent[0].content)
    assert body["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "extraction", "strict": True, "schema": expected},
    }
    assert body["provider"] == {
        "order": ["anthropic", "azure"],
        "require_parameters": True,
        "data_collection": "deny",
    }


def test_invalid_field_is_dropped_without_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    one_word = '{"full_name": "Lucía", "intent": "answer", "language": "es"}'
    llm, sent = openrouter(monkeypatch, completion(one_word))
    assert llm.extract(ASK).full_name is None
    assert len(sent) == 1


FAILED_REPLIES = {
    "malformed JSON": completion('{"intent": "answer"'),
    "invalid intent": completion('{"intent": "hire_me", "language": "es"}'),
    "HTTP 500": httpx2.Response(500),
    "error in a 200 body": httpx2.Response(
        200, json={"error": {"message": "Schema is too complex.", "code": 400}}
    ),
}


@pytest.mark.parametrize("failed", FAILED_REPLIES.values(), ids=FAILED_REPLIES.keys())
def test_extract_retries_once(
    monkeypatch: pytest.MonkeyPatch, failed: httpx2.Response
) -> None:
    llm, sent = openrouter(monkeypatch, failed, completion(VALID))
    assert llm.extract(ASK).has_license is True
    assert len(sent) == 2


def test_extract_raises_after_second_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    bad = completion("not json")
    llm, sent = openrouter(monkeypatch, bad, bad, completion(VALID))
    with pytest.raises(ValidationError):
        llm.extract(ASK)
    assert len(sent) == 2


def keepalive() -> Iterator[bytes]:
    """What OpenRouter streams while a call hangs, here forever."""
    while True:
        time.sleep(0.01)
        yield b"\n"


def test_extract_gives_up_on_a_call_that_never_ends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sazon.llm.TIMEOUT", 0.05)
    hung = [httpx2.Response(200, content=keepalive()) for _ in range(2)]
    llm, sent = openrouter(monkeypatch, *hung)
    with pytest.raises(httpx2.TimeoutException):
        llm.extract(ASK)
    assert len(sent) == 2


def test_phrase_returns_text_without_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    llm, sent = openrouter(monkeypatch, httpx2.Response(500), completion("¡Hola!"))
    assert llm.phrase(ASK) == "¡Hola!"
    assert "response_format" not in JSON_OBJECT.validate_json(sent[1].content)


def test_transcribe_sends_the_audio_to_scribe(monkeypatch: pytest.MonkeyPatch) -> None:
    usage = {"seconds": 1.2, "cost": 0.0001}
    heard = httpx2.Response(200, json={"text": "Sí, tengo carné", "usage": usage})
    llm, sent = openrouter(monkeypatch, heard)
    assert llm.transcribe(b"webm bytes", "webm") == "Sí, tengo carné"
    assert sent[0].url.path == "/api/v1/audio/transcriptions"
    audio = base64.b64encode(b"webm bytes").decode()
    assert JSON_OBJECT.validate_json(sent[0].content) == {
        "model": "elevenlabs/scribe-v2",
        "input_audio": {"data": audio, "format": "webm"},
        "provider": {"data_collection": "deny"},
    }


@pytest.mark.parametrize(
    ("text", "words"),
    [("[click]", ""), ("(risas) Sí, tengo carné.", "Sí, tengo carné.")],
    ids=["Leo's echo", "laughter"],
)
def test_transcribe_keeps_words_not_sounds(
    monkeypatch: pytest.MonkeyPatch, text: str, words: str
) -> None:
    llm, _ = openrouter(monkeypatch, httpx2.Response(200, json={"text": text}))
    assert llm.transcribe(b"webm bytes", "webm") == words


def test_transcribe_retries_once_then_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    error = httpx2.Response(200, json={"error": {"message": "Provider down"}})
    llm, sent = openrouter(monkeypatch, error, httpx2.Response(500))
    with pytest.raises(httpx2.HTTPStatusError):
        llm.transcribe(b"webm bytes", "webm")
    assert len(sent) == 2


@pytest.mark.parametrize(
    ("language", "voice"),
    [
        ("es", "es-MX-Grant:MAI-Voice-2.1-Flash"),
        ("en", "en-US-Grant:MAI-Voice-2.1-Flash"),
    ],
)
def test_speak_uses_grant_in_the_conversations_language(
    monkeypatch: pytest.MonkeyPatch, language: Language, voice: str
) -> None:
    mp3 = httpx2.Response(200, content=b"mp3 bytes")
    llm, sent = openrouter(monkeypatch, httpx2.Response(500), mp3)
    assert llm.speak("¿Tienes carné?", language) == b"mp3 bytes"
    assert sent[1].url.path == "/api/v1/audio/speech"
    assert JSON_OBJECT.validate_json(sent[1].content) == {
        "model": "microsoft/mai-voice-2.1-flash",
        "input": "¿Tienes carné?",
        "voice": voice,
        "response_format": "mp3",
        "provider": {"data_collection": "deny"},
    }


@pytest.mark.live
def test_live_extraction() -> None:
    llm = OpenRouter()
    with llm.client:
        extraction = llm.extract(
            [
                {
                    "role": "system",
                    "content": "Extract the screening fields present in the"
                    " candidate's message. Leave out fields not mentioned.",
                },
                {
                    "role": "user",
                    "content": "Hola, soy Lucía Pérez Gómez, tengo carnet de"
                    " conducir y vivo en Getafe.",
                },
            ]
        )
    assert extraction.full_name == "Lucía Pérez Gómez"
    assert extraction.has_license is True
    assert extraction.zone == "Getafe"
    assert (extraction.intent, extraction.language) == ("answer", "es")


@pytest.mark.live
def test_live_voice_round_trip() -> None:
    """Leo's voice back through speech-to-text. The browser records webm or m4a,
    which the 003 spike checked; this checks the client against the service."""
    llm = OpenRouter()
    with llm.client:
        audio = llm.speak("Tengo carné de conducir y vivo en Sevilla.", "es")
        heard = llm.transcribe(audio, "mp3")
    assert "sevilla" in heard.casefold()
