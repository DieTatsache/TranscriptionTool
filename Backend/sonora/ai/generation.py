"""Recap script and quiz generation from a transcript.

Short transcripts go to the model in one piece. Transcripts that don't fit the context
window are first condensed chunk by chunk into timestamped notes (map), and the script
and quiz are written from those notes (reduce).

Model output is never trusted as-is: it is normalised, bounded in size, timestamps are
snapped onto real transcript segments, and quiz options are de-duplicated and shuffled.
"""

import logging
import random
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sonora.ai import prompts
from sonora.ai.llm import LLMBadResponse, LLMClient
from sonora.ai.text import chunk_lines, estimate_tokens, transcript_lines
from sonora.ai.timestamps import format_timestamp, parse_timestamp, snap_to_segment

logger = logging.getLogger(__name__)

PROMPT_RESERVE_TOKENS = 800  # system prompt + schema overhead
OUTPUT_RESERVE_TOKENS = 2500  # room for the longest answer (script)
MAX_CONDENSE_ROUNDS = 3
_WS_RE = re.compile(r"\s+")


class GenerationError(Exception):
    """The model kept producing unusable output."""


@dataclass(frozen=True, slots=True)
class GeneratedContent:
    title: str
    script: dict[str, Any]
    quiz: list[dict[str, Any]]


def quiz_size(duration_seconds: float | None) -> int:
    """Roughly one question per five minutes, between 3 and 8."""
    return max(3, min(8, round((duration_seconds or 0) / 300)))


def clean_text(value: object, max_length: int) -> str:
    """Single-line, whitespace-normalised text cut at a word boundary."""
    if not isinstance(value, str):
        return ""
    text = _WS_RE.sub(" ", value).strip()
    if len(text) <= max_length:
        return text
    return text[: max_length - 1].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"


def normalize_script(raw: Mapping[str, Any], starts: Sequence[float]) -> dict[str, Any]:
    title = clean_text(raw.get("title"), 120).strip("\"'")
    summary = clean_text(raw.get("summary"), 600)
    overview_raw = raw.get("overview")
    overview = [
        p
        for p in (
            clean_text(x, 2000) for x in (overview_raw if isinstance(overview_raw, list) else [])
        )
        if p
    ][:6]

    takeaways: list[dict[str, Any]] = []
    seen: set[str] = set()
    items = raw.get("takeaways")
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, Mapping):
            continue
        text = clean_text(item.get("text"), 300)
        if not text or text.lower() in seen:
            continue
        seen.add(text.lower())
        at = snap_to_segment(parse_timestamp(item.get("timestamp")), starts)
        takeaways.append({"text": text, "at_seconds": at})
    takeaways = takeaways[:8]

    questions_raw = raw.get("questions")
    questions = [
        q
        for q in (
            clean_text(x, 200) for x in (questions_raw if isinstance(questions_raw, list) else [])
        )
        if q
    ][:4]

    if not (title and summary and overview and takeaways):
        raise GenerationError("script is missing required parts")
    return {
        "title": title,
        "summary": summary,
        "overview": overview,
        "takeaways": takeaways,
        "questions": questions,
    }


def _option_text(value: object) -> str:
    # Models tend to end only the correct answer with a period, which gives it away.
    text = clean_text(value, 200)
    return text[:-1].rstrip() if text.endswith(".") and not text.endswith("..") else text


def normalize_quiz(
    raw: Mapping[str, Any], starts: Sequence[float], *, limit: int, rng: random.Random
) -> list[dict[str, Any]]:
    items = raw.get("questions")
    quiz: list[dict[str, Any]] = []
    seen_questions: set[str] = set()
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, Mapping):
            continue
        question = clean_text(item.get("question"), 400)
        correct = _option_text(item.get("correct_answer"))
        wrong_raw = item.get("wrong_answers")
        if not question or not correct or question.lower() in seen_questions:
            continue
        options = [correct]
        for wrong in wrong_raw if isinstance(wrong_raw, list) else []:
            text = _option_text(wrong)
            if text and text.lower() not in {o.lower() for o in options}:
                options.append(text)
        options = options[:5]
        if len(options) < 3:
            continue
        seen_questions.add(question.lower())
        rng.shuffle(options)
        quiz.append(
            {
                "question": question,
                "options": options,
                "correct_option": options.index(correct),
                "explanation": clean_text(item.get("explanation"), 500),
                "source_seconds": snap_to_segment(parse_timestamp(item.get("timestamp")), starts),
            }
        )
        if len(quiz) == limit:
            break
    if len(quiz) < max(1, limit // 2):
        raise GenerationError(f"only {len(quiz)} usable quiz questions")
    return quiz


def notes_to_lines(raw: Mapping[str, Any]) -> list[str]:
    lines = []
    points = raw.get("points")
    for item in points if isinstance(points, list) else []:
        if not isinstance(item, Mapping):
            continue
        text = clean_text(item.get("point"), 400)
        at = parse_timestamp(item.get("timestamp"))
        if text and at is not None:
            lines.append(f"[{format_timestamp(at)}] {text}")
    if not lines:
        raise GenerationError("no usable notes")
    return lines


class ContentGenerator:
    def __init__(
        self,
        llm: LLMClient,
        *,
        context_tokens: int,
        attempts: int = 3,
        rng: random.Random | None = None,
    ) -> None:
        self._llm = llm
        self._budget = max(1000, context_tokens - PROMPT_RESERVE_TOKENS - OUTPUT_RESERVE_TOKENS)
        self._attempts = attempts
        self._rng = rng or random.SystemRandom()

    async def generate(
        self,
        segments: Sequence[Mapping[str, Any]],
        *,
        language: str | None,
        duration_seconds: float | None,
    ) -> GeneratedContent:
        if not segments:
            raise GenerationError("empty transcript")
        starts = [float(s["start"]) for s in segments]
        material = await self._fit_to_budget(transcript_lines(segments), language)

        async def script() -> dict[str, Any]:
            raw = await self._llm.complete_json(
                prompts.script_messages(material, language), prompts.SCRIPT_SCHEMA
            )
            return normalize_script(raw, starts)

        size = quiz_size(duration_seconds)

        async def quiz() -> list[dict[str, Any]]:
            raw = await self._llm.complete_json(
                prompts.quiz_messages(material, language, size), prompts.quiz_schema(size)
            )
            return normalize_quiz(raw, starts, limit=size, rng=self._rng)

        script_doc = await self._retrying(script)
        quiz_doc = await self._retrying(quiz)
        return GeneratedContent(title=script_doc["title"], script=script_doc, quiz=quiz_doc)

    async def _fit_to_budget(self, lines: list[str], language: str | None) -> list[str]:
        for _ in range(MAX_CONDENSE_ROUNDS):
            if self._fits(lines):
                return lines
            condensed: list[str] = []
            for chunk in chunk_lines(lines, self._budget):
                condensed.extend(await self._retrying(self._notes_for(chunk, language)))
            logger.info("condensed transcript from %d to %d lines", len(lines), len(condensed))
            if len(condensed) >= len(lines):
                break
            lines = condensed
        # Last resort for extreme lengths: keep an even sample of lines.
        while not self._fits(lines) and len(lines) > 1:
            lines = lines[::2]
        return lines

    def _fits(self, lines: Sequence[str]) -> bool:
        return estimate_tokens("\n".join(lines)) <= self._budget

    def _notes_for(
        self, chunk: Sequence[str], language: str | None
    ) -> Callable[[], Awaitable[list[str]]]:
        async def notes() -> list[str]:
            raw = await self._llm.complete_json(
                prompts.notes_messages(chunk, language), prompts.NOTES_SCHEMA
            )
            return notes_to_lines(raw)

        return notes

    async def _retrying[T](self, produce: Callable[[], Awaitable[T]]) -> T:
        # Bad output is retried here; LLMUnavailable propagates so the job backs off.
        last_error: Exception | None = None
        for attempt in range(1, self._attempts + 1):
            try:
                return await produce()
            except (LLMBadResponse, GenerationError) as exc:
                last_error = exc
                logger.warning("unusable model output (attempt %d): %s", attempt, exc)
        raise GenerationError(
            f"model output unusable after {self._attempts} attempts"
        ) from last_error
