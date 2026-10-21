"""Recruiter panel routes, with the fake LLM in place of OpenRouter."""

import threading
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx2
import pytest
from fastapi.testclient import TestClient

from fakes import FakeLLM, said
from sazon import api, storage
from sazon.api import app, get_agent
from sazon.llm import Message
from sazon.schema import Extraction
from sazon.turn import Agent, start, turn

LOGIN = ("recruiter", "test-password")

Step = tuple[str, Extraction]
START: Step = ("Sí, empecemos", said())
LICENCE: Step = ("Sí, tengo carné", said(has_license=True))
NO_LICENCE: Step = ("No tengo carné", said(has_license=False))
TOLEDO: Step = ("Toledo", said(zone="Toledo"))
WITHDRAW: Step = ("Ya no me interesa", said(intent="withdraw"))
PAY: Step = ("¿Cuánto pagan?", said(intent="question", question="other"))
MIXED: Step = ("Entre semana o findes, depende", said())  # no value: invalid
CONFIRMED: Step = ("Sí, todo bien", said(confirmed=True))
EXPERIENCE = {"years": 2, "platforms": ["glovo"]}
REST: list[Step] = [  # after availability, up to the recap
    ("Por la noche", said(preferred_schedule="evening")),
    ("Dos años en Glovo", said(prior_delivery_experience=EXPERIENCE)),
    ("En un mes", said(start_date=date.today() + timedelta(days=30))),
    CONFIRMED,
]
GETAFE_ANA: list[Step] = [
    START,
    LICENCE,
    ("Vivo en Getafe", said(zone="Getafe")),
    ("Ana López García", said(full_name="Ana López García")),
]
QUALIFIED = [*GETAFE_ANA, ("Media jornada", said(availability="part_time")), *REST]
NEEDS_REVIEW = [*GETAFE_ANA, MIXED, MIXED, MIXED, *REST]

# Every panel route, with a value for each path parameter. From the OpenAPI
# schema: app.routes does not list the routes of an included router.
PANEL_ROUTES = [
    (method.upper(), path.format(conversation_id="nope", asset="panel.js"))
    for path, operations in app.openapi()["paths"].items()
    if path.startswith("/panel")
    for method in operations
]


@pytest.fixture
def fake() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def agent(fake: FakeLLM, tmp_path: Path) -> Agent:
    db = tmp_path / "sazon.db"
    storage.create(db)
    return Agent(fake, db)


@pytest.fixture
def client(agent: Agent, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("PANEL_USER", LOGIN[0])
    monkeypatch.setenv("PANEL_PASSWORD", LOGIN[1])
    app.dependency_overrides[get_agent] = lambda: agent
    client = TestClient(app)  # without `with`, the lifespan (OpenRouter) never runs
    client.auth = LOGIN
    yield client
    app.dependency_overrides.clear()


def chat(client: TestClient, fake: FakeLLM, *steps: Step) -> str:
    """A candidate going through the chat API; returns the conversation id."""
    conversation_id = client.post("/conversations").json()["id"]
    for message, extraction in steps:
        fake.extractions[message] = extraction
        url = f"/conversations/{conversation_id}/messages"
        assert client.post(url, json={"text": message}).status_code == 200
    return conversation_id


@pytest.mark.parametrize(("method", "url"), PANEL_ROUTES)
@pytest.mark.parametrize(
    "login", [None, (LOGIN[0], "wrong"), ("wrong", LOGIN[1])], ids=str
)
@pytest.mark.usefixtures("client")
def test_every_panel_route_needs_the_login(
    method: str, url: str, login: tuple[str, str] | None
) -> None:
    stranger = TestClient(app)
    if login is not None:
        stranger.auth = login
    reply = stranger.request(method, url, json={})
    assert reply.status_code == 401
    assert reply.headers["www-authenticate"] == "Basic"


def test_panel_page_is_served_only_behind_the_login(client: TestClient) -> None:
    page = client.get("/panel")
    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/html")
    assert "frame-ancestors 'none'" in page.headers["content-security-policy"]
    assert client.get("/panel/panel.js").status_code == 200
    # Not in the public chat folder, so no path spelling reaches it there.
    assert client.get("/panel//index.html").status_code == 404


@pytest.mark.parametrize("password", ["", "contraseña"], ids=["blank", "non-ASCII"])
def test_app_fails_at_startup_without_a_usable_panel_login(
    monkeypatch: pytest.MonkeyPatch, agent: Agent, password: str
) -> None:
    monkeypatch.setattr(api, "get_agent", lambda: agent)
    monkeypatch.setenv("PANEL_USER", LOGIN[0])
    monkeypatch.setenv("PANEL_PASSWORD", password)
    with pytest.raises(RuntimeError, match="PANEL_PASSWORD"), TestClient(app):
        pass


def test_queue_order_and_derived_outcomes(
    client: TestClient, fake: FakeLLM, agent: Agent
) -> None:
    rejected = chat(client, fake, START, NO_LICENCE)
    review = chat(client, fake, *NEEDS_REVIEW)
    qualified = chat(client, fake, *QUALIFIED)
    withdrawn = chat(client, fake, START, WITHDRAW)
    chat(client, fake, START)  # still screening: not listed
    past = datetime.now(UTC) - timedelta(hours=73)
    abandoned, _ = start(agent, past)
    turn(agent, abandoned, START[0], past)
    rows = client.get("/panel/candidates").json()
    assert [(row["id"], row["outcome"]) for row in rows] == [
        (qualified, "qualified"),
        (review, "needs_review"),
        (rejected, "disqualified"),
        (withdrawn, "withdrawn"),
        (abandoned, "abandoned"),
    ]
    first, flagged, disqualified, _, stopped = rows
    assert (first["city"], first["country"], first["status"]) == (
        "Madrid",
        "ES",
        "pending",
    )
    assert flagged["flagged"] == ["availability"]
    assert disqualified["reason"] == "no_license"
    assert stopped["stopped"] == "license"
    detail = client.get(f"/panel/candidates/{abandoned}").json()
    assert detail["summary"].startswith("Full name: not given")
    assert detail["notes"] == []  # no closing, so no AI notes


def test_detail_keeps_the_code_summary_and_the_ai_notes_apart(
    client: TestClient, fake: FakeLLM
) -> None:
    conversation_id = chat(client, fake, START, PAY, *QUALIFIED[1:])
    detail = client.get(f"/panel/candidates/{conversation_id}").json()
    assert detail["summary"].startswith("Outcome: qualified\nFull name: Ana López")
    assert detail["summary"].endswith("Job questions for a recruiter: 1")
    assert detail["notes"] == ["First note."]
    assert detail["questions"] == ["¿Cuánto pagan?"]
    assert detail["fields"]["zone"] == "Getafe"
    assert detail["transcript"][1] == {
        "at": detail["transcript"][1]["at"],
        "role": "candidate",
        "text": START[0],
    }


def test_detail_tells_a_failed_note_from_none(
    client: TestClient, fake: FakeLLM
) -> None:
    fake.phrased = "NONE"  # the first answer closes, so the note is the only call
    nothing = chat(client, fake, NO_LICENCE)
    fake.phrased = httpx2.ConnectError("down")
    failed = chat(client, fake, NO_LICENCE)
    assert client.get(f"/panel/candidates/{nothing}").json()["notes"] == []
    assert client.get(f"/panel/candidates/{failed}").json()["notes"] is None


def test_status_is_saved_apart_from_the_outcome(
    client: TestClient, fake: FakeLLM
) -> None:
    url = f"/panel/candidates/{chat(client, fake, *QUALIFIED)}"
    changed = client.post(f"{url}/status", json={"status": "showed_up"}).json()
    assert changed["candidate"]["status"] == "showed_up"
    assert changed["candidate"]["outcome"] == "qualified"
    assert client.get(url).json() == changed


@pytest.mark.parametrize(
    "body", [{"status": "maybe"}, {"status": "hired", "extra": 1}, {}]
)
def test_invalid_status_is_rejected(
    client: TestClient, fake: FakeLLM, body: dict[str, object]
) -> None:
    url = f"/panel/candidates/{chat(client, fake, *QUALIFIED)}/status"
    assert client.post(url, json=body).status_code == 422


@pytest.mark.parametrize(
    "headers",
    [{"Content-Type": "text/plain"}, {"Content-Type": "multipart/form-data"}, {}],
    ids=["text", "form", "no content type"],
)
def test_writes_refuse_what_a_cross_site_page_can_send(
    client: TestClient, fake: FakeLLM, headers: dict[str, str]
) -> None:
    url = f"/panel/candidates/{chat(client, fake, START, NO_LICENCE)}"
    for action in ["status", "reopen"]:
        body = b'{"status": "hired"}'
        reply = client.post(f"{url}/{action}", content=body, headers=headers)
        assert reply.status_code == 415
    candidate = client.get(url).json()["candidate"]
    assert (candidate["outcome"], candidate["status"]) == ("disqualified", "pending")


def test_reopen_sends_a_disqualified_candidate_to_review_once(
    client: TestClient, fake: FakeLLM
) -> None:
    rejected = chat(client, fake, START, NO_LICENCE)
    qualified = chat(client, fake, *QUALIFIED)
    url = f"/panel/candidates/{rejected}/reopen"
    reopened = client.post(url, json={}).json()
    candidate = reopened["candidate"]
    assert (candidate["outcome"], candidate["reason"]) == ("needs_review", "no_license")
    assert candidate["reopened_at"] is not None
    # the screening's outcome is kept, for the reopened-rate guardrail (017)
    assert reopened["summary"].startswith("Outcome: disqualified (no_license)")
    assert client.post(url, json={}).status_code == 409
    assert (
        client.post(f"/panel/candidates/{qualified}/reopen", json={}).status_code == 409
    )
    rows = client.get("/panel/candidates").json()
    assert [row["outcome"] for row in rows] == ["qualified", "needs_review"]


@pytest.mark.parametrize(
    ("method", "action"), [("GET", ""), ("POST", "/status"), ("POST", "/reopen")]
)
def test_unknown_or_open_conversation_is_not_found(
    client: TestClient, fake: FakeLLM, method: str, action: str
) -> None:
    for conversation_id in ["nope", chat(client, fake, START)]:
        url = f"/panel/candidates/{conversation_id}{action}"
        reply = client.request(method, url, json={"status": "hired"})
        assert reply.status_code == 404


class HeldLLM(FakeLLM):
    """Holds each extraction until released, like a slow provider."""

    def __init__(self) -> None:
        super().__init__()
        self.waiting = threading.Event()
        self.release = threading.Event()

    def extract(self, messages: list[Message]) -> Extraction:
        self.waiting.set()
        self.release.wait(timeout=5)
        return super().extract(messages)


def test_status_change_during_a_turn_is_not_lost(
    client: TestClient, fake: FakeLLM, agent: Agent
) -> None:
    # zone_not_covered: a message after the close is the pool opt-in, an LLM call
    conversation_id = chat(client, fake, START, LICENCE, TOLEDO, TOLEDO)
    held = HeldLLM()
    held.extractions["Sí, avisadme"] = said(confirmed=True)
    candidate = threading.Thread(
        target=turn,
        args=(
            Agent(held, agent.db),
            conversation_id,
            "Sí, avisadme",
            datetime.now(UTC),
        ),
    )
    candidate.start()
    assert held.waiting.wait(timeout=5)
    recruiter = threading.Thread(
        target=client.post,
        args=(f"/panel/candidates/{conversation_id}/status",),
        kwargs={"json": {"status": "contacted"}},
    )
    recruiter.start()
    recruiter.join(timeout=0.2)  # unlocked, it saves now and the turn overwrites it
    held.release.set()
    candidate.join()
    recruiter.join()
    conversation = storage.load(agent.db, conversation_id)
    assert conversation is not None
    assert conversation.pool is not None
    assert conversation.recruiter_status == "contacted"
