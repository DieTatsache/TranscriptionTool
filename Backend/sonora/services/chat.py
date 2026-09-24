"""Lecture chat for session owners (not exposed to participants: LLM calls cost compute)."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sonora.ai.chat import LectureAssistant
from sonora.ai.llm import LLMError, LLMMessage
from sonora.container import Services
from sonora.db import utcnow
from sonora.errors import Conflict, ServiceUnavailable
from sonora.models import ChatMessage, ChatRole, SessionStatus, TrainingSession, User

HISTORY_LIMIT = 100
MESSAGES_PER_MINUTE = "10/minute"
MESSAGES_PER_DAY = "300/day"


async def history(db: AsyncSession, session: TrainingSession) -> list[ChatMessage]:
    rows = await db.scalars(
        select(ChatMessage)
        .where(ChatMessage.session_id == session.id)
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id)
        .limit(HISTORY_LIMIT)
    )
    return list(reversed(rows.all()))


def _as_llm_history(messages: Sequence[ChatMessage]) -> list[LLMMessage]:
    return [
        LLMMessage("user" if m.role is ChatRole.USER else "assistant", m.content) for m in messages
    ]


async def ask(
    db: AsyncSession, services: Services, owner: User, session: TrainingSession, question: str
) -> ChatMessage:
    """Answers ``question``; both turns are stored only if answering succeeded."""
    asked_at = utcnow()
    limiter = services.rate_limiter
    await limiter.hit(MESSAGES_PER_MINUTE, "chat", str(owner.id))
    await limiter.hit(MESSAGES_PER_DAY, "chat-day", str(owner.id))
    if session.status is not SessionStatus.READY or not session.transcript:
        raise Conflict("The session is still being processed.", code="session_not_ready")

    previous = await history(db, session)
    assistant = LectureAssistant(services.llm, context_tokens=services.settings.llm_context_tokens)
    try:
        answer = await assistant.answer(
            question=question,
            transcript=session.transcript,
            script=session.script,
            history=_as_llm_history(previous),
        )
    except LLMError as exc:
        raise ServiceUnavailable(
            "The assistant is not available right now. Please try again in a moment.",
            code="assistant_unavailable",
        ) from exc

    db.add(
        ChatMessage(
            session_id=session.id, role=ChatRole.USER, content=question, created_at=asked_at
        )
    )
    reply = ChatMessage(
        session_id=session.id,
        role=ChatRole.ASSISTANT,
        content=answer.text,
        source=answer.source,
        cite_seconds=answer.cite_seconds,
    )
    db.add(reply)
    await db.commit()
    return reply
