"""HTTP routes, with the fake LLM in place of OpenRouter."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fakes import PHRASED, FakeLLM, said
from sazon import storage
from sazon.api import app, get_agent
from sazon.templates import GREETING
from sazon.turn import CITIES, Agent


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


def test_app_fails_at_startup_without_an_api_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "sazon.db"))
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"), TestClient(app):
        pass
