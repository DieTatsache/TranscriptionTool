"""faster-whisper (CTranslate2) transcription.

Runs on CPU (int8) for development and on NVIDIA GPUs (float16) in production. The model
is loaded lazily once per process. ``model`` may be a size name, downloaded from Hugging
Face on first use, or a path to a local CTranslate2 model directory (offline setups).
"""

import logging
import threading
from pathlib import Path
from typing import Any

from sonora.transcription.base import (
    AudioTooLong,
    NoSpeechDetected,
    Segment,
    TranscriptionError,
    TranscriptionResult,
)

logger = logging.getLogger(__name__)


def probe_duration(path: Path) -> float | None:
    """Audio duration in seconds from container metadata, falling back to demuxing packets.

    Browser (MediaRecorder) WebM files often carry no duration header. Demuxing reads
    packet timestamps without decoding, so oversized files are rejected before the whole
    recording is decoded into memory.
    """
    import av  # bundled with faster-whisper

    try:
        with av.open(str(path), metadata_errors="ignore") as container:
            if container.duration:
                return float(container.duration / av.time_base)
            stream = next((s for s in container.streams if s.type == "audio"), None)
            if stream is None or stream.time_base is None:
                return None
            end = 0.0
            for packet in container.demux(stream):
                if packet.pts is not None:
                    end = max(end, float((packet.pts + (packet.duration or 0)) * stream.time_base))
            return end or None
    except (av.error.FFmpegError, OSError, ValueError) as exc:
        raise TranscriptionError("audio could not be read") from exc


class FasterWhisperTranscriber:
    def __init__(
        self,
        model: str,
        *,
        device: str = "auto",
        compute_type: str = "default",
        download_root: Path | None = None,
        beam_size: int = 5,
        cpu_threads: int = 0,
        default_language: str | None = None,
    ) -> None:
        self._model_name = model
        self._device = device
        self._compute_type = compute_type
        self._download_root = download_root
        self._beam_size = beam_size
        self._cpu_threads = cpu_threads
        self._default_language = default_language
        self._model: Any = None
        self._lock = threading.Lock()

    def _load(self) -> Any:
        with self._lock:
            if self._model is None:
                import ctranslate2
                from faster_whisper import WhisperModel

                device = self._device
                if device == "auto":
                    device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
                compute_type = self._compute_type
                if compute_type == "default":
                    compute_type = "float16" if device == "cuda" else "int8"
                logger.info(
                    "loading whisper model %s on %s (%s)", self._model_name, device, compute_type
                )
                self._model = WhisperModel(
                    self._model_name,
                    device=device,
                    compute_type=compute_type,
                    download_root=str(self._download_root) if self._download_root else None,
                    cpu_threads=self._cpu_threads,
                )
            return self._model

    def transcribe(
        self, path: Path, *, language: str | None, max_duration_seconds: float
    ) -> TranscriptionResult:
        duration = probe_duration(path)
        if duration is not None and duration > max_duration_seconds:
            raise AudioTooLong(f"{duration:.0f}s exceeds {max_duration_seconds:.0f}s")

        model = self._load()
        try:
            segments, info = model.transcribe(
                str(path),
                language=language or self._default_language,
                beam_size=self._beam_size,
                vad_filter=True,  # skips silence: faster, fewer hallucinated lines
            )
            if info.duration > max_duration_seconds:
                raise AudioTooLong(f"{info.duration:.0f}s exceeds {max_duration_seconds:.0f}s")
            result = [
                Segment(start=round(s.start, 2), end=round(s.end, 2), text=s.text.strip())
                for s in segments
                if s.text.strip()
            ]
        except TranscriptionError:
            raise
        except Exception as exc:  # decoder/runtime errors surface as many types
            raise TranscriptionError("audio could not be transcribed") from exc

        if not result:
            raise NoSpeechDetected("no speech detected")
        return TranscriptionResult(
            segments=result, language=info.language, duration_seconds=float(info.duration)
        )
