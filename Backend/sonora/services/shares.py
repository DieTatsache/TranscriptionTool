"""Participant share links: unguessable tokens granting read access to chosen tabs.

The set of visible tabs is stored server-side with the link, so participants can't widen
their access by editing the URL.
"""

import re
import uuid
from collections.abc import Sequence
from datetime import timedelta

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer
from sqlalchemy.sql.elements import ColumnElement

from sonora.db import rowcount, utcnow
from sonora.errors import Conflict, NotFound
from sonora.models import ActivityType, SessionStatus, ShareLink, ShareTab, TrainingSession, User
from sonora.security import new_token
from sonora.services import activity
from sonora.services.sessions import CONTENT_COLUMNS

MAX_LINKS_PER_SESSION = 20
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{32,64}$")


def _active() -> ColumnElement[bool]:
    return or_(ShareLink.expires_at.is_(None), ShareLink.expires_at > utcnow())


async def list_active(db: AsyncSession, session: TrainingSession) -> Sequence[ShareLink]:
    rows = await db.scalars(
        select(ShareLink)
        .where(ShareLink.session_id == session.id, _active())
        .order_by(ShareLink.created_at.desc())
    )
    return rows.all()


async def create(
    db: AsyncSession,
    owner: User,
    session: TrainingSession,
    *,
    tabs: Sequence[ShareTab],
    expires_in_days: int | None,
) -> ShareLink:
    if session.status is not SessionStatus.READY:
        raise Conflict("Only finished sessions can be shared.", code="session_not_ready")
    count = await db.scalar(
        select(func.count()).select_from(ShareLink).where(ShareLink.session_id == session.id)
    )
    if (count or 0) >= MAX_LINKS_PER_SESSION:
        raise Conflict(
            "This session has too many share links; revoke some first.", code="too_many_links"
        )
    ordered = [tab.value for tab in ShareTab if tab in set(tabs)]
    link = ShareLink(
        session_id=session.id,
        token=new_token(),
        tabs=ordered,
        created_at=utcnow(),
        expires_at=utcnow() + timedelta(days=expires_in_days) if expires_in_days else None,
    )
    db.add(link)
    activity.record(
        db, owner.id, ActivityType.SHARE_CREATED, f"{session.title} · {', '.join(ordered)}"
    )
    await db.commit()
    return link


async def revoke(
    db: AsyncSession, owner: User, session: TrainingSession, share_id: uuid.UUID
) -> None:
    result = await db.execute(
        delete(ShareLink).where(ShareLink.id == share_id, ShareLink.session_id == session.id)
    )
    if not rowcount(result):
        raise NotFound("Share link not found.", code="share_not_found")
    activity.record(db, owner.id, ActivityType.SHARE_REVOKED, session.title)
    await db.commit()


async def resolve(db: AsyncSession, token: str) -> tuple[ShareLink, TrainingSession]:
    """The link and its (ready) session; one generic 404 for unknown, expired or unready."""
    not_found = NotFound("This link is invalid or has expired.", code="share_not_found")
    if not _TOKEN_RE.fullmatch(token):
        raise not_found
    row = (
        await db.execute(
            select(ShareLink, TrainingSession)
            .join(TrainingSession, TrainingSession.id == ShareLink.session_id)
            .where(ShareLink.token == token, _active())
            .options(*(undefer(column) for column in CONTENT_COLUMNS))
        )
    ).first()
    if row is None or row[1].status is not SessionStatus.READY:
        raise not_found
    return row[0], row[1]
