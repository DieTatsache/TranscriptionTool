"""Portable column types (identical behaviour on SQLite and PostgreSQL)."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Dialect
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator[datetime]):
    """Timezone-aware UTC datetimes.

    PostgreSQL stores ``timestamptz``; SQLite has no time zones, so values are stored as
    naive UTC and re-attached to UTC when read. Naive input is rejected to catch bugs.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Naive datetime; use timezone-aware UTC values")
        value = value.astimezone(UTC)
        return value.replace(tzinfo=None) if dialect.name == "sqlite" else value

    def process_result_value(self, value: Any, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        stored: datetime = value
        return stored.replace(tzinfo=UTC) if stored.tzinfo is None else stored.astimezone(UTC)


# JSONB on PostgreSQL (indexable, compact), plain JSON text elsewhere.
JSONType = JSON().with_variant(JSONB(), "postgresql")
