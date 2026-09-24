"""Development stand-in for Whisper.

Returns the transcript of the first demo session for every upload, so the full pipeline
(upload, queue, LLM generation, UI) can be exercised without a speech model. It never
touches the audio and is rejected by the settings validation in production.
"""

from pathlib import Path

from sonora.demo import demo_sessions
from sonora.transcription.base import AudioTooLong, Segment, TranscriptionResult


class FakeTranscriber:
    def transcribe(
        self, path: Path, *, language: str | None, max_duration_seconds: float
    ) -> TranscriptionResult:
        sample = demo_sessions()[0]
        duration = float(sample["duration_seconds"])
        if duration > max_duration_seconds:
            raise AudioTooLong("sample transcript exceeds the configured limit")
        segments = [
            Segment(start=s["start"], end=s["end"], text=s["text"], speaker=s["speaker"])
            for s in sample["transcript"]
        ]
        return TranscriptionResult(segments=segments, language="en", duration_seconds=duration)
