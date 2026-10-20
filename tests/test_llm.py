import httpx2
import pytest
from pydantic import ValidationError

from sazon.llm import LLM, Message, OpenRouter
from sazon.schema import JSON_OBJECT, Extraction

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
    body = JSON_OBJECT.validate_json(sent[0].content)
    assert body["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "extraction", "strict": True, "schema": expected},
    }
    assert body["provider"] == {"require_parameters": True, "data_collection": "deny"}


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


def test_phrase_returns_text_without_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    llm, sent = openrouter(monkeypatch, httpx2.Response(500), completion("¡Hola!"))
    assert llm.phrase(ASK) == "¡Hola!"
    assert "response_format" not in JSON_OBJECT.validate_json(sent[1].content)


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
