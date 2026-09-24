"""Test doubles for the LLM and the transcriber."""

from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from typing import Any

from sonora.ai.llm import LLMMessage
from sonora.demo import demo_sessions
from sonora.transcription import Segment, TranscriptionResult

SAMPLE = demo_sessions()[0]  # "Handling Objections": segment starts 12, 41, 80, 88, ...

# Minimal RIFF/WAVE, WebM and unknown payloads; the fake transcriber never decodes them.
WEBM_AUDIO = b"\x1a\x45\xdf\xa3" + b"\x00" * 4096
WAV_AUDIO = b"RIFF\x24\x08\x00\x00WAVEfmt " + b"\x00" * 4096
NOT_AUDIO = b"%PDF-1.7\n" + b"\x00" * 4096


def script_output(title: str = "Handling Objections") -> dict[str, Any]:
    return {
        "title": title,
        "summary": "How to respond to objections under pressure.",
        "overview": [
            "An objection is a request for more information, not a rejection.",
            "Respond in sequence: acknowledge, ask, reframe.",
        ],
        "takeaways": [
            {"text": "An objection is not a rejection.", "timestamp": "00:41"},
            {"text": "Let silence do the work.", "timestamp": "[04:10]"},
            {"text": "Track your top three objections.", "timestamp": "05:30"},
        ],
        "questions": ["What is the three-step sequence?"],
    }


def quiz_output(count: int) -> dict[str, Any]:
    return {
        "questions": [
            {
                "question": f"Question {i + 1}?",
                "correct_answer": f"Right {i + 1}",
                "wrong_answers": [f"Wrong {i + 1}a", f"Wrong {i + 1}b", f"Wrong {i + 1}c"],
                "timestamp": "00:41",
                "explanation": "Because the trainer said so.",
            }
            for i in range(count)
        ]
    }


def default_output(schema: dict[str, Any]) -> dict[str, Any]:
    """A valid answer for whichever prompt the schema belongs to."""
    properties = schema.get("properties", {})
    if "takeaways" in properties:
        return script_output()
    if "questions" in properties:
        return quiz_output(properties["questions"]["minItems"])
    if "points" in properties:
        return {"points": [{"timestamp": "00:12", "point": "Objections deserve curiosity."}]}
    if "answer" in properties:
        return {"answer": "Wait a **full breath**.", "source": "lesson", "timestamp": "04:10"}
    raise AssertionError(f"unexpected schema: {sorted(properties)}")


Response = dict[str, Any] | Exception


class FakeLLM:
    """Records calls; replies from a queue of scripted responses, else a valid default."""

    def __init__(self) -> None:
        self.calls: list[tuple[list[LLMMessage], dict[str, Any]]] = []
        self.queue: list[Response] = []
        self.handler: Callable[[list[LLMMessage], dict[str, Any]], Response] | None = None
        # Awaited before every reply, e.g. to change the database mid-generation.
        self.before_reply: Callable[[], Awaitable[None]] | None = None
        self.available = True

    async def complete_json(
        self,
        messages: Sequence[LLMMessage],
        schema: dict[str, Any],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        self.calls.append((list(messages), schema))
        if self.before_reply is not None:
            await self.before_reply()
        if self.queue:
            response = self.queue.pop(0)
        elif self.handler is not None:
            response = self.handler(list(messages), schema)
        else:
            response = default_output(schema)
        if isinstance(response, Exception):
            raise response
        return response

    async def is_available(self) -> bool:
        return self.available

    async def aclose(self) -> None:
        pass


class FakeTranscriber:
    """Returns the demo transcript, or raises ``error`` when set."""

    def __init__(self) -> None:
        self.calls: list[Path] = []
        self.error: Exception | None = None
        self.language = "en"

    def transcribe(
        self, path: Path, *, language: str | None, max_duration_seconds: float
    ) -> TranscriptionResult:
        self.calls.append(path)
        if self.error is not None:
            raise self.error
        segments = [
            Segment(start=s["start"], end=s["end"], text=s["text"]) for s in SAMPLE["transcript"]
        ]
        return TranscriptionResult(
            segments=segments, language=self.language, duration_seconds=352.4
        )
