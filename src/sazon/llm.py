"""OpenRouter client (decision 002): the LLM extracts and phrases, code decides.
Voice goes through the same client (decision 003): speech-to-text and back.

turn.py depends on the LLM protocol, so tests pass a fake instead of OpenRouter.
"""

import base64
import os
import re
import time
from typing import Literal, Protocol, TypedDict

import httpx2
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

from sazon.schema import Extraction, Language, parse_extraction

MODEL = "anthropic/claude-haiku-5.5"
STT_MODEL = "elevenlabs/scribe-v2"
TTS_MODEL = "microsoft/mai-voice-2.1-flash"
# Grant in both languages; the locale fixes the synthesis language. MAI has no
# male es-ES voice, so Spain hears es-MX (decision 003).
SPANISH_VOICE = "es-MX-Grant:MAI-Voice-2.1-Flash"
ENGLISH_VOICE = "en-US-Grant:MAI-Voice-2.1-Flash"
# Scribe tags sounds, not words: "[click]" for Leo's echo, "(laughter)".
SOUNDS = re.compile(r"\[[^\]]*\]|\([^)]*\)")
# Observed 1.7-8.6 s per call. OpenRouter sends keep-alive whitespace while it
# waits, so a read timeout alone never fires: post() also checks a deadline
# after every read, and one attempt ends within 2 x TIMEOUT.
TIMEOUT = 15.0
FAILURES = (httpx2.HTTPError, ValidationError)


class Message(TypedDict):
    role: Literal["system", "user", "assistant"]
    content: str


class LLM(Protocol):
    def extract(self, messages: list[Message]) -> Extraction: ...

    def phrase(self, messages: list[Message]) -> str: ...

    def transcribe(self, audio: bytes, format: str) -> str: ...

    def speak(self, text: str, language: Language) -> bytes: ...


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


class Transcription(Envelope):
    text: str  # "" when the audio held no speech


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

    def transcribe(self, audio: bytes, format: str) -> str:
        """The words the candidate said, "" for none. One retry, then raises
        (decision 006)."""
        body: dict[str, object] = {
            "model": STT_MODEL,
            "input_audio": {"data": base64.b64encode(audio).decode(), "format": format},
            "provider": {"data_collection": "deny"},  # decision 014
        }
        try:
            heard = self.post("/audio/transcriptions", body)
            text = Transcription.model_validate_json(heard).text
        except FAILURES:
            heard = self.post("/audio/transcriptions", body)
            text = Transcription.model_validate_json(heard).text
        return SOUNDS.sub("", text).strip()

    def speak(self, text: str, language: Language) -> bytes:
        """MP3 of text in the conversation's language. One retry, then raises."""
        body: dict[str, object] = {
            "model": TTS_MODEL,
            "input": text,
            "voice": ENGLISH_VOICE if language == "en" else SPANISH_VOICE,
            "response_format": "mp3",
            "provider": {"data_collection": "deny"},  # decision 014
        }
        try:
            return self.post("/audio/speech", body)
        except FAILURES:
            return self.post("/audio/speech", body)

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
        # Some errors arrive as 200 with an "error" body: Completion rejects them.
        completion = Completion.model_validate_json(
            self.post("/chat/completions", body)
        )
        return completion.choices[0].message.content

    def post(self, path: str, body: dict[str, object]) -> bytes:
        """One attempt, over within 2 x TIMEOUT even while keep-alives arrive."""
        deadline = time.monotonic() + TIMEOUT
        content = b""
        with self.client.stream("POST", path, json=body) as response:
            response.raise_for_status()
            for chunk in response.iter_bytes():
                if time.monotonic() > deadline:
                    raise httpx2.ReadTimeout("deadline", request=response.request)
                content += chunk
        return content
