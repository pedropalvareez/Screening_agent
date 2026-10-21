"""OpenRouter client (decision 002): the LLM extracts and phrases, code decides.

turn.py depends on the LLM protocol, so tests pass a fake instead of OpenRouter.
"""

import os
import time
from typing import Literal, Protocol, TypedDict

import httpx2
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

from sazon.schema import Extraction, parse_extraction

MODEL = "anthropic/claude-haiku-5.5"
# Observed 1.7-8.6 s per call. OpenRouter sends keep-alive whitespace while it
# waits, so a read timeout alone never fires: complete() also checks a deadline
# after every read, and one attempt ends within 2 x TIMEOUT.
TIMEOUT = 15.0
FAILURES = (httpx2.HTTPError, ValidationError)


class Message(TypedDict):
    role: Literal["system", "user", "assistant"]
    content: str


class LLM(Protocol):
    def extract(self, messages: list[Message]) -> Extraction: ...

    def phrase(self, messages: list[Message]) -> str: ...


def for_model(node: JsonValue) -> JsonValue:
    """The schema without regexes and with every property required. The full-name
    regex fails with "Schema is too complex" after about 200 s, and with optional
    keys the model skips fields the message gave; a required key can still be null.
    parse_extraction enforces the rest."""
    if isinstance(node, dict):
        out = {
            k: for_model(v)
            for k, v in node.items()
            if not (k == "pattern" and isinstance(v, str))
        }
        if isinstance(properties := out.get("properties"), dict):
            out["required"] = [*properties]
        return out
    if isinstance(node, list):
        return [for_model(v) for v in node]
    return node


EXTRACTION_FORMAT: JsonValue = {
    "type": "json_schema",
    "json_schema": {
        "name": "extraction",
        "strict": True,
        "schema": for_model(Extraction.model_json_schema()),
    },
}


class Envelope(BaseModel):
    """OpenRouter's response varies by provider and over time: read only what we use."""

    model_config = ConfigDict(strict=True, extra="ignore")


class Text(Envelope):
    content: str = Field(min_length=1)


class Choice(Envelope):
    message: Text


class Completion(Envelope):
    choices: list[Choice] = Field(min_length=1)


class OpenRouter:
    def __init__(
        self, transport: httpx2.BaseTransport | None = None, model: str = MODEL
    ) -> None:
        self.model = model  # the evals' judge passes another one
        key = os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise RuntimeError(
                "OPENROUTER_API_KEY is not set: fill it in .env and pass"
                " --env-file .env to uv run or docker run"
            )
        self.client = httpx2.Client(
            base_url="https://openrouter.ai/api/v1",
            headers={"Authorization": f"Bearer {key}"},
            timeout=TIMEOUT,
            transport=transport,
        )

    def extract(self, messages: list[Message]) -> Extraction:
        """A screening field that fails its format is dropped by parse_extraction.
        Any other failure gets one retry, then raises (decision 006)."""
        try:
            return parse_extraction(self.complete(messages, EXTRACTION_FORMAT))
        except FAILURES:
            return parse_extraction(self.complete(messages, EXTRACTION_FORMAT))

    def phrase(self, messages: list[Message]) -> str:
        try:
            return self.complete(messages)
        except FAILURES:
            return self.complete(messages)

    def complete(
        self, messages: list[Message], response_format: JsonValue = None
    ) -> str:
        body: dict[str, object] = {
            "model": self.model,
            "messages": messages,
            "reasoning": {"effort": "low"},
            "provider": {
                # Fastest in the #6 spike (Vertex took 8 s); the rest stay fallbacks.
                "order": ["anthropic", "azure"],
                # Only providers that enforce response_format.
                "require_parameters": True,
                # No provider that trains on inputs (decision 014).
                "data_collection": "deny",
            },
        }
        if response_format is not None:
            body["response_format"] = response_format
        deadline = time.monotonic() + TIMEOUT
        content = b""
        with self.client.stream("POST", "/chat/completions", json=body) as response:
            response.raise_for_status()
            for chunk in response.iter_bytes():
                if time.monotonic() > deadline:
                    raise httpx2.ReadTimeout("deadline", request=response.request)
                content += chunk
        # Some errors arrive as 200 with an "error" body: Completion rejects them.
        completion = Completion.model_validate_json(content)
        return completion.choices[0].message.content
