"""Answers learner questions about one lecture, grounded in its transcript."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sonora.ai import prompts
from sonora.ai.generation import clean_text
from sonora.ai.llm import LLMBadResponse, LLMClient, LLMMessage
from sonora.ai.retrieval import build_passages, rank_passages
from sonora.ai.text import estimate_tokens, transcript_lines
from sonora.ai.timestamps import format_timestamp, parse_timestamp, snap_to_segment
from sonora.models import ChatSource

HISTORY_MESSAGES = 6
ANSWER_MAX_TOKENS = 600
RESERVED_TOKENS = 1500  # rules, history, question and the answer itself


@dataclass(frozen=True, slots=True)
class ChatAnswer:
    text: str
    source: ChatSource
    cite_seconds: int | None


def normalize_answer(raw: Mapping[str, Any], starts: Sequence[float]) -> ChatAnswer:
    # Answers are rendered as plain text + **bold** by the client; keep paragraphs short.
    text = raw.get("answer")
    text = text.strip()[:2000] if isinstance(text, str) else ""
    if not text:
        raise LLMBadResponse("empty chat answer")
    source = ChatSource.LESSON if raw.get("source") == "lesson" else ChatSource.KNOWLEDGE
    cite = None
    if source is ChatSource.LESSON:
        cite = snap_to_segment(parse_timestamp(raw.get("timestamp")), starts)
    return ChatAnswer(text=text, source=source, cite_seconds=cite)


class LectureAssistant:
    def __init__(self, llm: LLMClient, *, context_tokens: int) -> None:
        self._llm = llm
        self._material_budget = max(800, int((context_tokens - RESERVED_TOKENS) * 0.8))

    async def answer(
        self,
        *,
        question: str,
        transcript: Sequence[Mapping[str, Any]],
        script: Mapping[str, Any] | None,
        history: Sequence[LLMMessage],
    ) -> ChatAnswer:
        starts = [float(s["start"]) for s in transcript]
        messages = prompts.chat_messages(
            self.material(question, transcript, script), history[-HISTORY_MESSAGES:], question
        )
        try:
            raw = await self._llm.complete_json(
                messages, prompts.CHAT_SCHEMA, max_tokens=ANSWER_MAX_TOKENS
            )
            return normalize_answer(raw, starts)
        except LLMBadResponse:
            # One retry for malformed output; availability errors propagate.
            raw = await self._llm.complete_json(
                messages, prompts.CHAT_SCHEMA, max_tokens=ANSWER_MAX_TOKENS
            )
            return normalize_answer(raw, starts)

    def material(
        self,
        question: str,
        transcript: Sequence[Mapping[str, Any]],
        script: Mapping[str, Any] | None,
    ) -> str:
        """Summary + takeaways + the whole transcript if it fits, else the best passages."""
        parts: list[str] = []
        if script:
            parts.append("Summary: " + clean_text(script.get("summary"), 600))
            takeaways = [
                f"- [{format_timestamp(t['at_seconds'])}] {t['text']}"
                if t.get("at_seconds") is not None
                else f"- {t['text']}"
                for t in script.get("takeaways", [])
            ]
            if takeaways:
                parts.append("Key takeaways:\n" + "\n".join(takeaways))

        full = "\n".join(transcript_lines(transcript))
        if estimate_tokens(full) <= self._material_budget:
            parts.append("Transcript:\n<transcript>\n" + full + "\n</transcript>")
            return "\n\n".join(parts)

        picked = []
        used = 0
        for passage in rank_passages(build_passages(transcript), question):
            cost = estimate_tokens(passage.text)
            if used + cost > self._material_budget:
                break
            picked.append(passage)
            used += cost
        if picked:
            excerpt = "\n...\n".join(p.text for p in sorted(picked, key=lambda p: p.start))
            parts.append("Transcript excerpts:\n<transcript>\n" + excerpt + "\n</transcript>")
        else:
            parts.append("Transcript excerpts: none matched the question.")
        return "\n\n".join(parts)
