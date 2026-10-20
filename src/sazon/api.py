"""HTTP entry points. The LLM is reached only through turn.py."""

import functools
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import StringConstraints

from sazon import storage
from sazon.schema import Strict
from sazon.storage import Line
from sazon.turn import (
    Agent,
    Reply,
    UnknownConversation,
    connect,
    latest_reply,
    start,
    turn,
)


@functools.cache
def get_agent() -> Agent:
    return connect()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
    get_agent()  # fail at startup, not on the first candidate
    yield


app = FastAPI(title="Grupo Sazón screening", lifespan=lifespan)
AgentDep = Annotated[Agent, Depends(get_agent)]


class CandidateMessage(Strict):
    text: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)
    ]


class Started(Strict):
    id: str
    reply: Reply


class Resumed(Strict):
    """The chat after a reload: the transcript, then the last reply's options."""

    transcript: list[Line]
    reply: Reply


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/conversations")
def open_conversation(agent: AgentDep) -> Started:
    conversation_id, reply = start(agent, datetime.now(UTC))
    return Started(id=conversation_id, reply=reply)


@app.get("/conversations/{conversation_id}")
def resume(conversation_id: str, agent: AgentDep) -> Resumed:
    conversation = storage.load(agent.db, conversation_id)
    if conversation is None:
        raise HTTPException(404, "conversation not found")
    return Resumed(transcript=conversation.transcript, reply=latest_reply(conversation))


@app.post("/conversations/{conversation_id}/messages")
def send_message(
    conversation_id: str, message: CandidateMessage, agent: AgentDep
) -> Reply:
    try:
        return turn(agent, conversation_id, message.text, datetime.now(UTC))
    except UnknownConversation:
        raise HTTPException(404, "conversation not found") from None


# Last, so the routes above match first. The id travels in the URL fragment,
# which the browser never sends to the server.
app.mount("/", StaticFiles(directory=Path(__file__).parent / "web", html=True))
