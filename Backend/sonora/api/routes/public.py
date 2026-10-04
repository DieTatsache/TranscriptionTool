"""Unauthenticated endpoints for listeners holding a share link.

Listeners are anonymous. A random participant cookie lets the server count each browser's
first quiz attempt and feedback once; only a per-session hash of it is stored. The owner,
when signed in, is recognised and never counted as a listener.

Rate limits apply per client IP and per listener. The IP limits are sized for a lecture
hall where hundreds of listeners share one network address (NAT). The chat also has a
limit per lecture and a cap on answers generated at once, because every answer costs GPU
time that the owner's processing needs too.
"""

from typing import Annotated, TypeGuard

from fastapi import APIRouter, Path, Request, Response

from sonora.ai.llm import LLMMessage
from sonora.api.deps import (
    DB,
    ServicesDep,
    Viewer,
    issue_participant,
    rate_limit_ip,
    rate_limit_participant,
    read_participant,
)
from sonora.api.schemas import (
    FeedbackFormOut,
    FeedbackQuestionOut,
    FeedbackSubmit,
    PublicChatAnswer,
    PublicChatAsk,
    PublicShare,
    QuizCheckRequest,
    QuizQuestion,
    QuizResultOut,
    Script,
    TranscriptSegment,
)
from sonora.errors import BadRequest, NotFound, PermissionDenied, ServiceUnavailable
from sonora.feedback import FEEDBACK_FORM, FORM_VERSION
from sonora.models import ShareTab, TrainingSession, User
from sonora.security import participant_key
from sonora.services import chat as chat_service
from sonora.services import feedback as feedback_service
from sonora.services import quiz as quiz_service
from sonora.services import shares as shares_service

router = APIRouter(prefix="/public", tags=["public"])

Token = Annotated[str, Path(min_length=1, max_length=128)]

READS_PER_IP = "600/minute"
QUIZ_CHECKS_PER_IP = "300/minute"
QUIZ_CHECKS_PER_LISTENER = "30/minute"
FEEDBACK_PER_IP = "600/hour"
FEEDBACK_PER_LISTENER = "10/hour"
CHAT_PER_IP = "300/hour"
CHAT_PER_LISTENER = "5/minute"
CHAT_PER_LISTENER_DAY = "60/day"
CHAT_PER_LECTURE = "600/hour"  # all listeners of one session together
# Tabs that need the participant cookie (counting answers, limiting the chat per listener).
LISTENER_TABS = {ShareTab.QUIZ, ShareTab.FEEDBACK, ShareTab.CHAT}


def _is_owner(viewer: User | None, session: TrainingSession) -> TypeGuard[User]:
    return viewer is not None and viewer.id == session.owner_id


def _tab_not_shared() -> NotFound:
    # Same answer as for an unknown link: nothing reveals what else exists.
    return NotFound("This link is invalid or has expired.", code="share_not_found")


@router.get(
    "/shares/{token}",
    response_model=PublicShare,
    dependencies=[rate_limit_ip(READS_PER_IP, "public-share")],
)
async def get_shared_session(
    token: Token,
    request: Request,
    response: Response,
    db: DB,
    services: ServicesDep,
    viewer: Viewer,
) -> PublicShare:
    link, session = await shares_service.resolve(db, token)
    tabs = set(link.tabs)
    is_owner = _is_owner(viewer, session)
    feedback_submitted = False
    if not is_owner and tabs & LISTENER_TABS:
        # Only links where listeners answer or chat set the (anonymous) participant cookie.
        settings = services.settings
        participant = read_participant(request, settings) or issue_participant(response, settings)
        if ShareTab.FEEDBACK in tabs:
            feedback_submitted = await feedback_service.has_responded(
                db, session.id, participant_key(session.id, participant)
            )
    return PublicShare(
        title=session.title,
        created_at=session.created_at,
        duration_seconds=session.duration_seconds,
        language=session.language,
        tabs=[ShareTab(t) for t in link.tabs],
        # Only what the trainer chose to share leaves the server.
        script=Script.model_validate(session.script)
        if ShareTab.SCRIPT in tabs and session.script
        else None,
        quiz=[QuizQuestion.model_validate(q) for q in quiz_service.public_questions(session.quiz)]
        if ShareTab.QUIZ in tabs and session.quiz
        else None,
        transcript=[TranscriptSegment.model_validate(s) for s in session.transcript]
        if ShareTab.TRANSCRIPT in tabs and session.transcript
        else None,
        feedback_form=FeedbackFormOut(
            version=FORM_VERSION, questions=[FeedbackQuestionOut.of(q) for q in FEEDBACK_FORM]
        )
        if ShareTab.FEEDBACK in tabs
        else None,
        feedback_submitted=feedback_submitted,
        viewer_is_owner=is_owner,
    )


@router.post(
    "/shares/{token}/quiz/check",
    response_model=QuizResultOut,
    dependencies=[
        rate_limit_ip(QUIZ_CHECKS_PER_IP, "public-quiz"),
        rate_limit_participant(QUIZ_CHECKS_PER_LISTENER, "public-quiz-listener"),
    ],
)
async def check_shared_quiz(
    token: Token,
    body: QuizCheckRequest,
    request: Request,
    db: DB,
    services: ServicesDep,
    viewer: Viewer,
) -> QuizResultOut:
    link, session = await shares_service.resolve(db, token)
    if ShareTab.QUIZ not in link.tabs:
        raise _tab_not_shared()
    result = quiz_service.grade(session.quiz, body.answers)
    counted = False
    participant = read_participant(request, services.settings)
    if participant is not None and not _is_owner(viewer, session):
        counted = await quiz_service.record_first_attempt(
            db, session, participant_key(session.id, participant), body.answers, result
        )
    return QuizResultOut.model_validate(result).model_copy(update={"counted": counted})


@router.post(
    "/shares/{token}/feedback",
    status_code=204,
    dependencies=[
        rate_limit_ip(FEEDBACK_PER_IP, "public-feedback"),
        rate_limit_participant(FEEDBACK_PER_LISTENER, "public-feedback-listener"),
    ],
)
async def submit_feedback(
    token: Token,
    body: FeedbackSubmit,
    request: Request,
    db: DB,
    services: ServicesDep,
    viewer: Viewer,
) -> Response:
    link, session = await shares_service.resolve(db, token)
    if ShareTab.FEEDBACK not in link.tabs:
        raise _tab_not_shared()
    if _is_owner(viewer, session):
        raise PermissionDenied(
            "Feedback is collected from your listeners, not from you.", code="own_session"
        )
    participant = read_participant(request, services.settings)
    if participant is None:  # the share page sets it; cookies blocked or a scripted client
        raise BadRequest(
            "Please reload the page (cookies must be enabled) and try again.",
            code="participant_required",
        )
    await feedback_service.submit(
        db,
        session,
        participant_key(session.id, participant),
        ratings=body.ratings,
        comment=body.comment,
    )
    return Response(status_code=204)


@router.post(
    "/shares/{token}/chat",
    response_model=PublicChatAnswer,
    dependencies=[
        rate_limit_ip(CHAT_PER_IP, "public-chat"),
        rate_limit_participant(CHAT_PER_LISTENER, "public-chat-listener"),
        rate_limit_participant(CHAT_PER_LISTENER_DAY, "public-chat-listener-day"),
    ],
)
async def ask_shared_chat(
    token: Token,
    body: PublicChatAsk,
    request: Request,
    db: DB,
    services: ServicesDep,
    viewer: Viewer,
) -> PublicChatAnswer:
    link, session = await shares_service.resolve(db, token)
    if ShareTab.CHAT not in link.tabs:
        raise _tab_not_shared()
    if _is_owner(viewer, session):
        # The owner trying out their link has no listener cookie: their own chat limits apply.
        await chat_service.limit_owner(services, viewer)
    elif read_participant(request, services.settings) is None:
        raise BadRequest(
            "Please reload the page (cookies must be enabled) and try again.",
            code="participant_required",
        )
    await services.rate_limiter.hit(
        CHAT_PER_LECTURE,
        "public-chat-lecture",
        str(session.id),
        message="Many listeners are asking right now. Please try again in a few minutes.",
    )
    slots = services.public_chat_slots
    if slots.locked():
        raise ServiceUnavailable(
            "The assistant is busy right now. Please try again in a minute.",
            code="assistant_busy",
        )
    history = [LLMMessage(turn.role, turn.content) for turn in body.history]
    async with slots:
        answer = await chat_service.answer_listener(services, session, body.message, history)
    return PublicChatAnswer(
        answer=answer.text, source=answer.source, cite_seconds=answer.cite_seconds
    )
