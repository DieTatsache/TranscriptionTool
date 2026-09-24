"""Transcript formatting, token budgeting and chunking."""

import math
from collections.abc import Mapping, Sequence
from typing import Any

from sonora.ai.timestamps import format_timestamp

LANGUAGE_NAMES = {
    "cs": "Czech", "da": "Danish", "de": "German", "en": "English", "es": "Spanish",
    "fi": "Finnish", "fr": "French", "it": "Italian", "nl": "Dutch", "no": "Norwegian",
    "pl": "Polish", "pt": "Portuguese", "ru": "Russian", "sv": "Swedish", "tr": "Turkish",
    "uk": "Ukrainian",
}  # fmt: skip


def estimate_tokens(text: str) -> int:
    # ~3 characters per token is conservative for German/English with Llama-style tokenizers.
    return max(1, math.ceil(len(text) / 3))


def transcript_lines(segments: Sequence[Mapping[str, Any]]) -> list[str]:
    return [f"[{format_timestamp(s['start'])}] {s['text']}" for s in segments]


def chunk_lines(lines: Sequence[str], max_tokens: int) -> list[list[str]]:
    """Greedily packs lines into chunks of at most ``max_tokens`` (never splits a line)."""
    chunks: list[list[str]] = []
    current: list[str] = []
    used = 0
    for line in lines:
        cost = estimate_tokens(line) + 1
        if current and used + cost > max_tokens:
            chunks.append(current)
            current, used = [], 0
        current.append(line)
        used += cost
    if current:
        chunks.append(current)
    return chunks


def language_instruction(code: str | None) -> str:
    name = LANGUAGE_NAMES.get((code or "").lower())
    if name:
        return f"Write every text field in {name}."
    return "Write every text field in the same language as the transcript."
