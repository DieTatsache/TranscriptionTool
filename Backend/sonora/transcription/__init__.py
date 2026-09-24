"""Speech-to-text backends behind the ``Transcriber`` protocol."""

from sonora.config import Settings, TranscriptionBackend
from sonora.transcription.base import (
    AudioTooLong,
    NoSpeechDetected,
    Segment,
    Transcriber,
    TranscriptionError,
    TranscriptionResult,
)


def build_transcriber(settings: Settings) -> Transcriber:
    if settings.transcription_backend is TranscriptionBackend.FAKE:
        from sonora.transcription.fake import FakeTranscriber

        return FakeTranscriber()

    # Imported lazily: faster-whisper is an optional (worker-only) dependency.
    from sonora.transcription.whisper import FasterWhisperTranscriber

    return FasterWhisperTranscriber(
        settings.whisper_model,
        device=settings.whisper_device,
        compute_type=settings.whisper_compute_type,
        download_root=settings.whisper_model_dir,
        beam_size=settings.whisper_beam_size,
        cpu_threads=settings.whisper_cpu_threads,
        default_language=settings.whisper_language,
    )


__all__ = [
    "AudioTooLong",
    "NoSpeechDetected",
    "Segment",
    "Transcriber",
    "TranscriptionError",
    "TranscriptionResult",
    "build_transcriber",
]
