"""ORM models. Importing this package registers every table on ``Base.metadata``."""

from sonora.models.activity import ActivityEvent, ActivityType
from sonora.models.auth_session import AuthSession
from sonora.models.chat import ChatMessage, ChatRole, ChatSource
from sonora.models.job import Job, JobStatus, JobType
from sonora.models.share import ShareLink, ShareTab
from sonora.models.training_session import SessionStatus, TrainingSession
from sonora.models.user import User

__all__ = [
    "ActivityEvent",
    "ActivityType",
    "AuthSession",
    "ChatMessage",
    "ChatRole",
    "ChatSource",
    "Job",
    "JobStatus",
    "JobType",
    "SessionStatus",
    "ShareLink",
    "ShareTab",
    "TrainingSession",
    "User",
]
