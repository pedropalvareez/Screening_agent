"""HTTP entry points. The LLM is reached only through turn.py."""

import functools
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from pydantic import StringConstraints

from sazon.schema import Strict
from sazon.turn import Agent, Reply, UnknownConversation, connect, start, turn


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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/conversations")
def open_conversation(agent: AgentDep) -> Started:
    conversation_id, reply = start(agent, datetime.now(UTC))
    return Started(id=conversation_id, reply=reply)


@app.post("/conversations/{conversation_id}/messages")
def send_message(
    conversation_id: str, message: CandidateMessage, agent: AgentDep
) -> Reply:
    try:
        return turn(agent, conversation_id, message.text, datetime.now(UTC))
    except UnknownConversation:
        raise HTTPException(404, "conversation not found") from None
