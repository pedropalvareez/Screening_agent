"""HTTP routes, with the fake LLM in place of OpenRouter."""

from collections.abc import Iterator
from pathlib import Path

import httpx2
import pytest
from fastapi.testclient import TestClient

from fakes import PHRASED, FakeLLM, said
from sazon import storage
from sazon.api import MAX_AUDIO, app, get_agent
from sazon.templates import GREETING
from sazon.turn import CITIES, Agent

WEBM = {"Content-Type": "audio/webm;codecs=opus"}  # what Chrome records


@pytest.fixture
def fake() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def client(fake: FakeLLM, tmp_path: Path) -> Iterator[TestClient]:
    db = tmp_path / "sazon.db"
    storage.create(db)
    app.dependency_overrides[get_agent] = lambda: Agent(fake, db)
    yield TestClient(app)  # without `with`, the lifespan (OpenRouter) never runs
    app.dependency_overrides.clear()


def test_agent_writes_first_then_answers(client: TestClient, fake: FakeLLM) -> None:
    started = client.post("/conversations").json()
    assert started["reply"] == {"text": GREETING, "options": None, "language": "es"}
    fake.extractions["Sí, empecemos"] = said()
    url = f"/conversations/{started['id']}/messages"
    reply = client.post(url, json={"text": "  Sí, empecemos "})
    assert reply.json() == {"text": PHRASED, "options": None, "language": "es"}


def test_reload_resumes_the_transcript_and_the_city_options(
    client: TestClient, fake: FakeLLM
) -> None:
    conversation_id = client.post("/conversations").json()["id"]
    url = f"/conversations/{conversation_id}"
    fake.extractions["Sí"] = said()
    fake.extractions["Tengo carné"] = said(has_license=True)
    fake.extractions["Toledo"] = said(zone="Toledo")
    for text in ["Sí", "Tengo carné", "Toledo"]:
        last = client.post(f"{url}/messages", json={"text": text}).json()
    assert last["options"] == CITIES
    resumed = client.get(url).json()
    assert resumed["reply"] == last
    lines = [(line["role"], line["text"]) for line in resumed["transcript"]]
    assert lines[:2] == [("agent", GREETING), ("candidate", "Sí")]
    assert lines[-1] == ("agent", last["text"])
    assert len(lines) == 7


@pytest.mark.parametrize(
    ("method", "url"),
    [("GET", "/conversations/nope"), ("POST", "/conversations/nope/messages")],
)
def test_unknown_conversation_is_not_found(
    client: TestClient, method: str, url: str
) -> None:
    reply = client.request(method, url, json={"text": "Hola"})
    assert reply.status_code == 404


def test_root_serves_the_chat(client: TestClient) -> None:
    page = client.get("/")
    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/html")


@pytest.mark.parametrize(
    "body",
    [{"text": " "}, {"text": "a" * 1001}, {"text": "Hola", "extra": 1}],
    ids=["blank", "too long", "extra key"],
)
def test_invalid_message_is_rejected(
    client: TestClient, body: dict[str, object]
) -> None:
    conversation_id = client.post("/conversations").json()["id"]
    url = f"/conversations/{conversation_id}/messages"
    assert client.post(url, json=body).status_code == 422


@pytest.mark.parametrize(
    ("content_type", "audio_format"),
    [("audio/webm;codecs=opus", "webm"), ("audio/mp4", "m4a")],
    ids=["Chrome", "Safari"],
)
def test_transcription_returns_the_text_and_stores_nothing(
    client: TestClient, fake: FakeLLM, content_type: str, audio_format: str
) -> None:
    url = f"/conversations/{client.post('/conversations').json()['id']}"
    headers = {"Content-Type": content_type}
    heard = client.post(f"{url}/transcription", content=b"audio", headers=headers)
    assert heard.json() == {"text": "Sí, tengo carné"}
    assert fake.recordings == [(b"audio", audio_format)]
    # The browser sends the text as a message: no turn ran.
    assert len(client.get(url).json()["transcript"]) == 1


def test_transcription_caps_the_size_and_the_formats(
    client: TestClient, fake: FakeLLM
) -> None:
    conversation_id = client.post("/conversations").json()["id"]
    url = f"/conversations/{conversation_id}/transcription"
    full = client.post(url, content=b"0" * MAX_AUDIO, headers=WEBM)
    assert full.status_code == 200
    too_long = client.post(url, content=b"0" * (MAX_AUDIO + 1), headers=WEBM)
    assert too_long.status_code == 413
    ogg = client.post(url, content=b"audio", headers={"Content-Type": "audio/ogg"})
    assert ogg.status_code == 415
    assert len(fake.recordings) == 1


def test_speech_says_the_latest_reply_without_links_or_emoji(
    client: TestClient, fake: FakeLLM
) -> None:
    url = f"/conversations/{client.post('/conversations').json()['id']}"
    spoken = client.get(f"{url}/speech")
    assert spoken.content == b"fake mp3"
    assert spoken.headers["content-type"] == "audio/mpeg"
    assert spoken.headers["cache-control"] == "no-store"
    # The sentence with the privacy link and the parentheses stay on screen.
    assert fake.spoken == [
        (
            "¡Hola! Soy Leo, el asistente virtual de Grupo Sazón. Te haré unas"
            " preguntas sobre tu solicitud de repartidor: unos 2 minutos. ¿Empezamos?",
            "es",
        )
    ]
    fake.extractions["Yes, let's start"] = said(language="en")
    fake.phrased = "Great 👍 Do you have a driving licence?"
    client.post(f"{url}/messages", json={"text": "Yes, let's start"})
    client.get(f"{url}/speech")
    text, language = fake.spoken[-1]
    assert language == "en"
    assert "👍" not in text and text.endswith("Do you have a driving licence?")


def test_voice_failures_leave_the_chat_as_it_was(
    client: TestClient, fake: FakeLLM
) -> None:
    url = f"/conversations/{client.post('/conversations').json()['id']}"
    fake.heard = httpx2.ConnectError("down")
    heard = client.post(f"{url}/transcription", content=b"audio", headers=WEBM)
    assert heard.status_code == 502
    fake.extractions["Sí"] = said()
    reply = client.post(f"{url}/messages", json={"text": "Sí"}).json()
    fake.audio = httpx2.ReadTimeout("deadline")
    assert client.get(f"{url}/speech").status_code == 502
    resumed = client.get(url).json()
    assert resumed["reply"] == reply  # saved before the speech failed
    assert [line["text"] for line in resumed["transcript"][1:]] == ["Sí", PHRASED]


def test_voice_needs_a_known_conversation(client: TestClient, fake: FakeLLM) -> None:
    url = "/conversations/nope"
    heard = client.post(f"{url}/transcription", content=b"audio", headers=WEBM)
    assert heard.status_code == 404
    assert client.get(f"{url}/speech").status_code == 404
    assert not fake.recordings and not fake.spoken


def test_app_fails_at_startup_without_an_api_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "sazon.db"))
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"), TestClient(app):
        pass
