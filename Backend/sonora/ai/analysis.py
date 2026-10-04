"""Lecture analysis for the lecturer: scores for content, rhetoric and structure (1-10),
and how long the lecture stayed on each topic.

The model only judges: it writes the assessments and scores and names where each topic
starts. Everything measurable (topic durations, speaking pace) is computed here from the
transcript, and topic starts are snapped onto real segments, so the time shares are exact.
"""

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sonora.ai import prompts
from sonora.ai.generation import (
    GenerationError,
    clean_text,
    material_budget,
    prepare_material,
    retrying,
)
from sonora.ai.llm import LLMClient, Sampling
from sonora.ai.timestamps import parse_timestamp, snap_to_segment

logger = logging.getLogger(__name__)

MAX_TOPICS = 12
MIN_PACE_SECONDS = 60  # shorter recordings give no meaningful words-per-minute figure
# Measured on sample lectures with Qwen3.5-9B: reasoning ("thinking") gave the same scores
# at 7-9x the time and tokens, so these calls don't think. A presence penalty pushes the
# model away from digits it has already written (scores, timestamps) and caused outliers.
# Single judgements still vary by about one point, so each score is the median of a few:
# one stray judgement can't skew it (the repeats reuse the cached prompt).
JUDGE_SAMPLING = Sampling(temperature=0.3, presence_penalty=0.0)
TOPICS_SAMPLING = Sampling(presence_penalty=0.0)
SCORE_JUDGEMENTS = 3
SCORES_MAX_TOKENS = 1500  # observed 400-600; a cap stops runaway output early
TOPICS_MAX_TOKENS = 1000


@dataclass(frozen=True, slots=True)
class LectureAnalysis:
    scores: dict[str, dict[str, Any]]
    topics: list[dict[str, Any]]
    metrics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"scores": self.scores, "topics": self.topics, "metrics": self.metrics}


def _end(segment: Mapping[str, Any]) -> float:
    return float(segment.get("end", segment["start"]))


def speaking_metrics(segments: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    words = sum(len(str(s["text"]).split()) for s in segments)
    span = max(_end(s) for s in segments) - float(segments[0]["start"])
    pace = round(words / (span / 60)) if span >= MIN_PACE_SECONDS else None
    return {"words": words, "words_per_minute": pace}


def normalize_scores(raw: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    scores: dict[str, dict[str, Any]] = {}
    for category in prompts.SCORE_CATEGORIES:
        item = raw.get(category)
        if not isinstance(item, Mapping):
            raise GenerationError(f"missing {category} score")
        score = item.get("score")
        if isinstance(score, float) and score.is_integer():
            score = int(score)
        if isinstance(score, bool) or not isinstance(score, int) or not 1 <= score <= 10:
            raise GenerationError(f"invalid {category} score: {score!r}")
        assessment = clean_text(item.get("assessment"), 700)
        if not assessment:
            raise GenerationError(f"missing {category} assessment")
        scores[category] = {
            "score": score,
            "assessment": assessment,
            "tip": clean_text(item.get("tip"), 300),
        }
    return scores


def median_judgement(
    judgements: Sequence[Mapping[str, dict[str, Any]]],
) -> dict[str, dict[str, Any]]:
    """Per category the median score, with the assessment of the judgement that gave it."""
    combined: dict[str, dict[str, Any]] = {}
    for category in prompts.SCORE_CATEGORIES:
        ranked = sorted((j[category] for j in judgements), key=lambda item: item["score"])
        combined[category] = ranked[(len(ranked) - 1) // 2]
    return combined


def normalize_topics(
    raw: Mapping[str, Any], segments: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Chronological, non-overlapping topics that cover the lecture from start to end."""
    starts = [float(s["start"]) for s in segments]
    items = raw.get("topics")
    found: list[tuple[int, str]] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, Mapping):
            continue
        title = clean_text(item.get("title"), 80).strip("\"'")
        at = snap_to_segment(parse_timestamp(item.get("start")), starts)
        if title and at is not None:
            found.append((at, title))
    found.sort(key=lambda topic: topic[0])  # stable: equal starts keep the model's order

    merged: list[tuple[int, str]] = []
    for at, title in found:
        if merged and (at == merged[-1][0] or title.lower() == merged[-1][1].lower()):
            continue  # same start, or the model split one topic in two
        merged.append((at, title))
    merged = merged[:MAX_TOPICS]
    if not merged:
        raise GenerationError("no usable topics")

    lecture_start = int(starts[0])
    lecture_end = max(round(max(_end(s) for s in segments)), lecture_start + 1)
    merged[0] = (lecture_start, merged[0][1])  # the opening belongs to the first topic
    topics = []
    for index, (at, title) in enumerate(merged):
        end = merged[index + 1][0] if index + 1 < len(merged) else lecture_end
        if end > at:  # a zero-length last segment would give an empty topic
            topics.append(
                {
                    "title": title,
                    "start_seconds": at,
                    "end_seconds": end,
                    "duration_seconds": end - at,
                }
            )
    return topics


class LectureAnalyzer:
    def __init__(self, llm: LLMClient, *, context_tokens: int, attempts: int = 3) -> None:
        self._llm = llm
        self._budget = material_budget(context_tokens)
        self._attempts = attempts

    async def analyze(
        self, segments: Sequence[Mapping[str, Any]], *, language: str | None
    ) -> LectureAnalysis:
        if not segments:
            raise GenerationError("empty transcript")
        metrics = speaking_metrics(segments)
        material = await prepare_material(
            self._llm, segments, language=language, budget=self._budget, attempts=self._attempts
        )

        async def topics() -> list[dict[str, Any]]:
            raw = await self._llm.complete_json(
                prompts.topics_messages(material, language),
                prompts.TOPICS_SCHEMA,
                max_tokens=TOPICS_MAX_TOKENS,
                sampling=TOPICS_SAMPLING,
            )
            return normalize_topics(raw, segments)

        async def scores() -> dict[str, dict[str, Any]]:
            raw = await self._llm.complete_json(
                prompts.scores_messages(
                    material, language, words_per_minute=metrics["words_per_minute"]
                ),
                prompts.SCORES_SCHEMA,
                max_tokens=SCORES_MAX_TOKENS,
                sampling=JUDGE_SAMPLING,
            )
            return normalize_scores(raw)

        topic_list = await retrying(topics, attempts=self._attempts)
        judgements = [
            await retrying(scores, attempts=self._attempts) for _ in range(SCORE_JUDGEMENTS)
        ]
        return LectureAnalysis(
            scores=median_judgement(judgements), topics=topic_list, metrics=metrics
        )
