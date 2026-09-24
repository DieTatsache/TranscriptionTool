import sys
import types
import wave
from collections.abc import Iterator
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest

from sonora.config import TranscriptionBackend
from sonora.transcription import (
    AudioTooLong,
    NoSpeechDetected,
    TranscriptionError,
    build_transcriber,
)
from sonora.transcription.fake import FakeTranscriber
from tests.conftest import make_settings

av = pytest.importorskip("av", reason="needs the 'transcription' extra")

from sonora.transcription import whisper  # noqa: E402  (requires av)


def write_wav(path: Path, seconds: float, rate: int = 16000) -> Path:
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(b"\x00\x00" * int(rate * seconds))
    return path


class TestProbeDuration:
    def test_reads_the_container_duration(self, tmp_path: Path) -> None:
        assert whisper.probe_duration(write_wav(tmp_path / "a.wav", 2.5)) == pytest.approx(
            2.5, abs=0.05
        )

    def test_rejects_unreadable_files(self, tmp_path: Path) -> None:
        bogus = tmp_path / "bogus.webm"
        bogus.write_bytes(b"\x1a\x45\xdf\xa3" + b"\x00" * 64)
        with pytest.raises(TranscriptionError):
            whisper.probe_duration(bogus)

    def test_falls_back_to_packet_timestamps(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # MediaRecorder WebM files often lack a duration header.
        @dataclass
        class Packet:
            pts: int | None
            duration: int | None

        stream = types.SimpleNamespace(type="audio", time_base=Fraction(1, 1000))

        class Container:
            duration = None
            streams = [stream]

            def __enter__(self) -> "Container":
                return self

            def __exit__(self, *_: object) -> None:
                pass

            def demux(self, _stream: object) -> Iterator[Packet]:
                yield from (Packet(0, 20), Packet(None, None), Packet(61_000, 20))

        monkeypatch.setattr(av, "open", lambda *_a, **_k: Container())
        assert whisper.probe_duration(Path("x.webm")) == pytest.approx(61.02)

        Container.streams = []
        assert whisper.probe_duration(Path("x.webm")) is None


@dataclass
class FakeSegment:
    start: float
    end: float
    text: str


class FakeWhisperModel:
    instances: list["FakeWhisperModel"] = []
    segments: list[FakeSegment] = []
    duration = 10.0
    error: Exception | None = None

    def __init__(self, name: str, **kwargs: Any) -> None:
        self.name, self.kwargs = name, kwargs
        self.transcribe_kwargs: dict[str, Any] = {}
        FakeWhisperModel.instances.append(self)

    def transcribe(self, path: str, **kwargs: Any) -> tuple[Iterator[FakeSegment], Any]:
        self.transcribe_kwargs = kwargs
        if self.error:
            raise self.error
        info = types.SimpleNamespace(language="de", duration=self.duration)
        return iter(self.segments), info


@pytest.fixture
def fake_whisper(monkeypatch: pytest.MonkeyPatch) -> type[FakeWhisperModel]:
    FakeWhisperModel.instances = []
    FakeWhisperModel.segments = [
        FakeSegment(0.004, 2.5, " Hallo zusammen. "),
        FakeSegment(2.5, 3.0, "  "),
    ]
    FakeWhisperModel.duration = 10.0
    FakeWhisperModel.error = None
    monkeypatch.setitem(
        sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=FakeWhisperModel)
    )
    return FakeWhisperModel


class TestFasterWhisperTranscriber:
    def test_transcribes_and_maps_segments(
        self, tmp_path: Path, fake_whisper: type[FakeWhisperModel]
    ) -> None:
        transcriber = whisper.FasterWhisperTranscriber("small", download_root=tmp_path, beam_size=3)
        audio = write_wav(tmp_path / "a.wav", 1.0)

        result = transcriber.transcribe(audio, language="de", max_duration_seconds=60)

        assert [(s.start, s.end, s.text, s.speaker) for s in result.segments] == [
            (0.0, 2.5, "Hallo zusammen.", "Speaker")
        ]
        assert result.language == "de"
        assert result.duration_seconds == 10.0
        (model,) = fake_whisper.instances
        assert model.name == "small"
        assert model.kwargs["device"] == "cpu"  # no GPU in CI / on this machine
        assert model.kwargs["compute_type"] == "int8"
        assert model.kwargs["download_root"] == str(tmp_path)
        assert model.transcribe_kwargs == {"language": "de", "beam_size": 3, "vad_filter": True}

    def test_loads_the_model_once(
        self, tmp_path: Path, fake_whisper: type[FakeWhisperModel]
    ) -> None:
        transcriber = whisper.FasterWhisperTranscriber(
            "large-v3-turbo", device="cuda", default_language="en"
        )
        audio = write_wav(tmp_path / "a.wav", 1.0)
        transcriber.transcribe(audio, language=None, max_duration_seconds=60)
        transcriber.transcribe(audio, language=None, max_duration_seconds=60)
        (model,) = fake_whisper.instances
        assert model.kwargs["compute_type"] == "float16"
        assert model.transcribe_kwargs["language"] == "en"

    def test_rejects_long_audio_before_loading_the_model(
        self, tmp_path: Path, fake_whisper: type[FakeWhisperModel]
    ) -> None:
        transcriber = whisper.FasterWhisperTranscriber("small")
        with pytest.raises(AudioTooLong):
            transcriber.transcribe(
                write_wav(tmp_path / "a.wav", 3.0), language=None, max_duration_seconds=2
            )
        assert fake_whisper.instances == []

    def test_rejects_long_audio_detected_while_decoding(
        self, tmp_path: Path, fake_whisper: type[FakeWhisperModel]
    ) -> None:
        fake_whisper.duration = 999.0
        with pytest.raises(AudioTooLong):
            whisper.FasterWhisperTranscriber("small").transcribe(
                write_wav(tmp_path / "a.wav", 1.0), language=None, max_duration_seconds=60
            )

    def test_silence_means_no_speech(
        self, tmp_path: Path, fake_whisper: type[FakeWhisperModel]
    ) -> None:
        fake_whisper.segments = [FakeSegment(0, 1, "   ")]
        with pytest.raises(NoSpeechDetected):
            whisper.FasterWhisperTranscriber("small").transcribe(
                write_wav(tmp_path / "a.wav", 1.0), language=None, max_duration_seconds=60
            )

    def test_decoder_errors_become_transcription_errors(
        self, tmp_path: Path, fake_whisper: type[FakeWhisperModel]
    ) -> None:
        fake_whisper.error = RuntimeError("Invalid data found when processing input")
        with pytest.raises(TranscriptionError):
            whisper.FasterWhisperTranscriber("small").transcribe(
                write_wav(tmp_path / "a.wav", 1.0), language=None, max_duration_seconds=60
            )


def test_fake_transcriber_returns_the_demo_transcript(tmp_path: Path) -> None:
    result = FakeTranscriber().transcribe(tmp_path / "x", language=None, max_duration_seconds=3600)
    assert result.segments[0].text.startswith("Welcome back everyone.")
    assert result.language == "en"
    with pytest.raises(AudioTooLong):
        FakeTranscriber().transcribe(tmp_path / "x", language=None, max_duration_seconds=60)


def test_build_transcriber_selects_the_backend(tmp_path: Path) -> None:
    assert isinstance(build_transcriber(make_settings(tmp_path)), FakeTranscriber)
    real = build_transcriber(
        make_settings(
            tmp_path,
            transcription_backend=TranscriptionBackend.FASTER_WHISPER,
            whisper_model="base",
        )
    )
    assert isinstance(real, whisper.FasterWhisperTranscriber)
