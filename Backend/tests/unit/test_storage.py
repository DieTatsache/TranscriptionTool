import os
import time
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from sonora.errors import BadRequest, RequestTooLarge, UnsupportedMediaType
from sonora.storage import AudioStorage, sniff_audio_format


@pytest.mark.parametrize(
    ("head", "extension"),
    [
        (b"\x1a\x45\xdf\xa3\x01\x00", "webm"),
        (b"OggS\x00\x02", "ogg"),
        (b"RIFF\x24\x08\x00\x00WAVEfmt ", "wav"),
        (b"fLaC\x00\x00\x00\x22", "flac"),
        (b"\x00\x00\x00\x20ftypM4A ", "m4a"),
        (b"ID3\x04\x00\x00", "mp3"),
        (b"\xff\xfb\x90\x64", "mp3"),  # MPEG-1 layer III frame
        (b"\xff\xf1\x50\x80", "aac"),  # ADTS
    ],
)
def test_sniffs_supported_containers(head: bytes, extension: str) -> None:
    detected = sniff_audio_format(head)
    assert detected is not None and detected.extension == extension


@pytest.mark.parametrize(
    "head",
    [b"%PDF-1.7", b"MZ\x90\x00", b"<html>", b"RIFF\x00\x00\x00\x00AVI ", b"\xff", b"", b"\x7fELF"],
)
def test_rejects_everything_else(head: bytes) -> None:
    assert sniff_audio_format(head) is None


async def chunks(*parts: bytes) -> AsyncIterator[bytes]:
    for part in parts:
        yield part


@pytest.fixture
def storage(tmp_path: Path) -> AudioStorage:
    return AudioStorage(tmp_path)


async def test_streams_upload_to_a_random_name(storage: AudioStorage) -> None:
    stored = await storage.save_stream(
        chunks(b"\x1a\x45", b"\xdf\xa3" + b"a" * 20, b"b" * 2000), max_bytes=10_000
    )
    assert stored.format.extension == "webm"
    assert stored.size == 2024
    path = storage.path_for(stored.key)
    assert path.read_bytes().startswith(b"\x1a\x45\xdf\xa3")
    assert [p.name for p in storage.directory.iterdir()] == [stored.key]


async def test_unsupported_data_is_rejected_early_and_cleaned_up(storage: AudioStorage) -> None:
    with pytest.raises(UnsupportedMediaType):
        await storage.save_stream(chunks(b"%PDF-1.7 " * 10, b"x" * 5000), max_bytes=100_000)
    assert list(storage.directory.iterdir()) == []


async def test_tiny_uploads_are_checked_at_the_end(storage: AudioStorage) -> None:
    with pytest.raises(UnsupportedMediaType):
        await storage.save_stream(chunks(b"MZ"), max_bytes=100)
    with pytest.raises(BadRequest):
        await storage.save_stream(chunks(b"OggS" + b"\x00" * 100), max_bytes=10_000)
    assert list(storage.directory.iterdir()) == []


async def test_size_limit_is_enforced_while_streaming(storage: AudioStorage) -> None:
    with pytest.raises(RequestTooLarge):
        await storage.save_stream(chunks(b"OggS" + b"\x00" * 3000, b"\x00" * 3000), max_bytes=5000)
    assert list(storage.directory.iterdir()) == []


@pytest.mark.parametrize(
    "key",
    ["../secret.webm", "..\\x.webm", "abc.webm", "0" * 32 + ".exe", "0" * 32 + ".webm/../../x", ""],
)
def test_keys_cannot_escape_the_directory(storage: AudioStorage, key: str) -> None:
    with pytest.raises(ValueError, match="invalid storage key"):
        storage.path_for(key)


def test_delete_is_best_effort(storage: AudioStorage) -> None:
    storage.delete(None)
    storage.delete("0" * 32 + ".webm")  # missing: no error
    storage.delete("../../etc/passwd")  # invalid: logged, no error


def test_delete_orphans(storage: AudioStorage) -> None:
    old = time.time() - 3600
    live, orphan, recent = (storage.directory / f"{c * 32}.webm" for c in "abc")
    for path in (live, orphan, recent):
        path.write_bytes(b"x")
    for path in (live, orphan):
        os.utime(path, (old, old))
    (storage.directory / "subdir").mkdir()

    removed = storage.delete_orphans([live.name], older_than_seconds=60)

    assert removed == 1
    assert sorted(p.name for p in storage.directory.iterdir()) == sorted(
        [live.name, recent.name, "subdir"]
    )
