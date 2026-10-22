"""A scripted stand-in for the LLM: no network, no key."""

from sazon.llm import Message
from sazon.schema import Extraction, Intent, Language

# Every phrased reply; parsed as the summary note, only its first line is kept.
PHRASED = "First note.\nSecond note."


class FakeLLM:
    """Implements the LLM protocol. extract() answers each candidate message as
    scripted in `extractions`; phrase() returns `phrased`, transcribe() `heard`
    and speak() `audio`. Calls are recorded."""

    def __init__(self) -> None:
        self.extractions: dict[str, Extraction | Exception] = {}
        self.phrased: str | Exception = PHRASED
        self.heard: str | Exception = "Sí, tengo carné"
        self.audio: bytes | Exception = b"fake mp3"
        self.calls: list[list[Message]] = []
        self.recordings: list[tuple[bytes, str]] = []  # transcribe(audio, format)
        self.spoken: list[tuple[str, Language]] = []  # speak(text, language)

    def transcribe(self, audio: bytes, format: str) -> str:
        self.recordings.append((audio, format))
        if isinstance(self.heard, Exception):
            raise self.heard
        return self.heard

    def speak(self, text: str, language: Language) -> bytes:
        self.spoken.append((text, language))
        if isinstance(self.audio, Exception):
            raise self.audio
        return self.audio

    def extract(self, messages: list[Message]) -> Extraction:
        self.calls.append(messages)
        result = self.extractions[messages[-1]["content"]]
        if isinstance(result, Exception):
            raise result
        return result

    def phrase(self, messages: list[Message]) -> str:
        self.calls.append(messages)
        if isinstance(self.phrased, Exception):
            raise self.phrased
        return self.phrased


def said(
    intent: Intent = "answer", language: Language = "es", **fields: object
) -> Extraction:
    """What the LLM extracts from one candidate message."""
    return Extraction.model_validate({"intent": intent, "language": language, **fields})
