"""Request and response models.

Every inbound string has a maximum length, and user-provided text is stripped of control
and bidi-override characters (log/UI spoofing). Quiz answers only appear in grading
results, never in the models used to display a quiz.
"""

import re
import uuid
from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field, StringConstraints

from sonora.ai.text import LANGUAGE_NAMES
from sonora.models import ActivityType, ChatRole, ChatSource, SessionStatus, ShareTab

_BIDI_OVERRIDES = dict.fromkeys(
    [*range(0x202A, 0x202F), *range(0x2066, 0x206A)], None
)  # LRE..RLO, LRI..PDI
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def _single_line(value: str) -> str:
    value = _CONTROL_RE.sub(" ", value.replace("\n", " ")).translate(_BIDI_OVERRIDES)
    return " ".join(value.split())


def _multi_line(value: str) -> str:
    value = _CONTROL_RE.sub("", value.replace("\r\n", "\n")).translate(_BIDI_OVERRIDES)
    return re.sub(r"\n{3,}", "\n\n", value).strip()


def _required(value: str) -> str:
    if not value:
        raise ValueError("must not be empty")
    return value


def _known_language(value: str | None) -> str | None:
    if value is not None and value not in LANGUAGE_NAMES:
        raise ValueError("unsupported language")
    return value


Name = Annotated[
    str, StringConstraints(max_length=100), AfterValidator(_single_line), AfterValidator(_required)
]
Title = Annotated[str, StringConstraints(max_length=200), AfterValidator(_single_line)]
Bio = Annotated[str, StringConstraints(max_length=1000), AfterValidator(_multi_line)]
Email = EmailStr  # email-validator enforces RFC length limits (254 chars)
Password = Annotated[str, StringConstraints(min_length=1, max_length=128)]
ChatText = Annotated[
    str, StringConstraints(max_length=1000), AfterValidator(_multi_line), AfterValidator(_required)
]
Language = Annotated[str | None, AfterValidator(_known_language)]


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Accounts ----------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    name: Name
    email: Email
    password: Password


class LoginRequest(BaseModel):
    # Plain string: a malformed address simply fails to sign in.
    email: Annotated[str, StringConstraints(min_length=1, max_length=254)]
    password: Password


class UserOut(_Out):
    id: uuid.UUID
    name: str
    email: str
    bio: str
    plan: str
    notify_on_ready: bool
    created_at: datetime


class AuthResponse(BaseModel):
    user: UserOut
    # Echo in X-CSRF-Token on every state-changing request.
    csrf_token: str


class ProfileUpdate(BaseModel):
    name: Name | None = None
    bio: Bio | None = None
    notify_on_ready: bool | None = None
    email: Email | None = None
    # Required when the email changes.
    current_password: Password | None = None


class PasswordChange(BaseModel):
    current_password: Password
    new_password: Password


class AccountDelete(BaseModel):
    password: Password


class PlanOut(_Out):
    id: str
    name: str
    monthly_price_cents: int
    monthly_session_limit: int | None


class UsageOut(BaseModel):
    plan: PlanOut
    sessions_this_month: int
    remaining_this_month: int | None


class StatsOut(_Out):
    total_sessions: int
    quiz_questions: int
    audio_seconds: int
    sessions_this_month: int


class ActivityOut(_Out):
    type: ActivityType
    detail: str
    created_at: datetime


# --- Sessions ----------------------------------------------------------------------------


class SessionSummary(_Out):
    id: uuid.UUID
    title: str
    status: SessionStatus
    error_message: str | None
    language: str | None
    duration_seconds: int | None
    quiz_count: int
    created_at: datetime
    ready_at: datetime | None


class TranscriptSegment(BaseModel):
    start: float
    end: float
    speaker: str
    text: str


class Takeaway(BaseModel):
    text: str
    at_seconds: int | None


class Script(BaseModel):
    title: str
    summary: str
    overview: list[str]
    takeaways: list[Takeaway]
    questions: list[str] = []


class QuizQuestion(BaseModel):
    question: str
    options: list[str]


class SessionDetail(SessionSummary):
    script: Script | None = None
    quiz: list[QuizQuestion] | None = None
    transcript: list[TranscriptSegment] | None = None


class QuizCheckRequest(BaseModel):
    answers: list[Annotated[int, Field(ge=0, le=9)] | None] = Field(max_length=50)


class QuestionResultOut(_Out):
    selected: int | None
    correct_option: int
    is_correct: bool
    explanation: str
    source_seconds: int | None


class QuizResultOut(_Out):
    score: int
    total: int
    results: list[QuestionResultOut]


# --- Chat --------------------------------------------------------------------------------


class ChatAsk(BaseModel):
    message: ChatText


class ChatMessageOut(_Out):
    id: uuid.UUID
    role: ChatRole
    content: str
    source: ChatSource | None
    cite_seconds: int | None
    created_at: datetime


# --- Sharing -----------------------------------------------------------------------------


class ShareCreate(BaseModel):
    tabs: list[ShareTab] = Field(min_length=1, max_length=len(ShareTab))
    # null = never expires
    expires_in_days: int | None = Field(default=30, ge=1, le=365)


class ShareOut(_Out):
    id: uuid.UUID
    token: str
    tabs: list[ShareTab]
    created_at: datetime
    expires_at: datetime | None


class PublicShare(BaseModel):
    title: str
    created_at: datetime
    duration_seconds: int | None
    language: str | None
    tabs: list[ShareTab]
    script: Script | None = None
    quiz: list[QuizQuestion] | None = None
    transcript: list[TranscriptSegment] | None = None


# --- Meta --------------------------------------------------------------------------------


class LanguageOut(BaseModel):
    code: str
    name: str


class MetaOut(BaseModel):
    version: str
    registration_enabled: bool
    password_min_length: int
    max_upload_mb: int
    max_audio_minutes: int
    languages: list[LanguageOut]
    share_tabs: list[ShareTab]
