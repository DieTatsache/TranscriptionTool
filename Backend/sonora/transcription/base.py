from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol


class TranscriptionError(Exception):
    """The audio cannot be transcribed (permanent: retrying won't help)."""


class AudioTooLong(TranscriptionError):
    pass


class NoSpeechDetected(TranscriptionError):
    pass


@dataclass(frozen=True, slots=True)
class Segment:
    start: float
    end: float
    text: str
    # No diarization yet; kept in the data model so it can be added without a migration.
    speaker: str = "Speaker"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class TranscriptionResult:
    segments: list[Segment]
    language: str | None
    duration_seconds: float


class Transcriber(Protocol):
    def transcribe(
        self, path: Path, *, language: str | None, max_duration_seconds: float
    ) -> TranscriptionResult:
        """Blocking and CPU/GPU heavy: call from a worker thread."""
        ...
