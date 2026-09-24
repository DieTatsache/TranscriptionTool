"""Audio file storage on the local filesystem (a volume shared by API and worker).

Uploads are streamed to disk with a hard size limit and identified by their magic bytes,
never by client-supplied names or content types. Files get random server-side names, and
keys are validated before use so no path can escape the storage directory.
"""

import logging
import re
import time
import uuid
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass
from pathlib import Path

import anyio

from sonora.errors import BadRequest, RequestTooLarge, UnsupportedMediaType

logger = logging.getLogger(__name__)

MIN_AUDIO_BYTES = 1024
_SNIFF_BYTES = 16
_KEY_RE = re.compile(r"^[0-9a-f]{32}\.(webm|ogg|wav|mp3|m4a|flac|aac)$")


@dataclass(frozen=True, slots=True)
class AudioFormat:
    extension: str
    mime: str


def sniff_audio_format(head: bytes) -> AudioFormat | None:
    """Identifies supported audio containers from their first bytes."""
    if head.startswith(b"\x1a\x45\xdf\xa3"):
        return AudioFormat("webm", "audio/webm")  # WebM/Matroska (Chrome, Firefox)
    if head.startswith(b"OggS"):
        return AudioFormat("ogg", "audio/ogg")
    if head.startswith(b"RIFF") and head[8:12] == b"WAVE":
        return AudioFormat("wav", "audio/wav")
    if head.startswith(b"fLaC"):
        return AudioFormat("flac", "audio/flac")
    if head[4:8] == b"ftyp":
        return AudioFormat("m4a", "audio/mp4")  # MP4/M4A (Safari recordings, phones)
    if head.startswith(b"ID3"):
        return AudioFormat("mp3", "audio/mpeg")
    if len(head) >= 2 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0:
        # Frame sync: layer bits 00 mean AAC (ADTS), anything else is MPEG audio.
        if head[1] & 0x06 == 0:
            return AudioFormat("aac", "audio/aac")
        return AudioFormat("mp3", "audio/mpeg")
    return None


@dataclass(frozen=True, slots=True)
class StoredAudio:
    key: str
    format: AudioFormat
    size: int


class AudioStorage:
    def __init__(self, root: Path) -> None:
        self.directory = root / "audio"
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)

    def path_for(self, key: str) -> Path:
        if not _KEY_RE.fullmatch(key):
            raise ValueError("invalid storage key")
        return self.directory / key

    async def save_stream(self, chunks: AsyncIterator[bytes], *, max_bytes: int) -> StoredAudio:
        """Streams an upload to disk. Raises before accepting unsupported or oversized data."""
        file_id = uuid.uuid4().hex
        partial = self.directory / f"{file_id}.part"
        size = 0
        head = b""
        audio_format: AudioFormat | None = None
        try:
            async with await anyio.open_file(partial, "wb") as out:
                async for chunk in chunks:
                    size += len(chunk)
                    if size > max_bytes:
                        raise RequestTooLarge()
                    if audio_format is None:
                        head += chunk
                        if len(head) >= _SNIFF_BYTES:
                            audio_format = self._require_format(head)
                    await out.write(chunk)
            if audio_format is None:
                audio_format = self._require_format(head)
            if size < MIN_AUDIO_BYTES:
                raise BadRequest("The recording is empty or too short.", code="audio_too_short")
            key = f"{file_id}.{audio_format.extension}"
            final = partial.replace(self.directory / key)
            final.chmod(0o600)
        except BaseException:
            partial.unlink(missing_ok=True)
            raise
        return StoredAudio(key=key, format=audio_format, size=size)

    @staticmethod
    def _require_format(head: bytes) -> AudioFormat:
        audio_format = sniff_audio_format(head)
        if audio_format is None:
            raise UnsupportedMediaType(
                "Unsupported audio format. Use WebM, Ogg, MP3, M4A, WAV, FLAC or AAC.",
                code="unsupported_audio",
            )
        return audio_format

    def delete(self, key: str | None) -> None:
        if not key:
            return
        try:
            self.path_for(key).unlink(missing_ok=True)
        except (OSError, ValueError):
            # Best effort (e.g. file still open on Windows); the orphan sweep retries later.
            logger.warning("could not delete audio file %s", key, exc_info=True)

    def delete_orphans(self, keys_in_use: Iterable[str], *, older_than_seconds: float) -> int:
        """Removes files no session references (and stale partial uploads)."""
        in_use = set(keys_in_use)
        cutoff = time.time() - older_than_seconds
        removed = 0
        for path in self.directory.iterdir():
            if path.name in in_use or not path.is_file():
                continue
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink()
                    removed += 1
            except OSError:
                logger.warning("could not remove orphaned file %s", path.name, exc_info=True)
        return removed
