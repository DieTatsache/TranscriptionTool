from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy.dialects import postgresql, sqlite

from sonora.db.types import UTCDateTime

CET = timezone(timedelta(hours=1))


def test_naive_datetimes_are_rejected() -> None:
    with pytest.raises(ValueError, match="Naive datetime"):
        UTCDateTime().process_bind_param(datetime(2026, 1, 1), sqlite.dialect())


def test_values_are_stored_as_utc() -> None:
    local = datetime(2026, 9, 24, 13, 0, tzinfo=CET)
    on_sqlite = UTCDateTime().process_bind_param(local, sqlite.dialect())
    on_postgres = UTCDateTime().process_bind_param(local, postgresql.dialect())
    assert on_sqlite == datetime(2026, 9, 24, 12, 0)  # naive UTC: SQLite has no time zones
    assert on_postgres == datetime(2026, 9, 24, 12, 0, tzinfo=UTC)
    assert UTCDateTime().process_bind_param(None, sqlite.dialect()) is None


def test_values_are_read_back_as_aware_utc() -> None:
    naive = UTCDateTime().process_result_value(datetime(2026, 9, 24, 12, 0), sqlite.dialect())
    aware = UTCDateTime().process_result_value(
        datetime(2026, 9, 24, 14, 0, tzinfo=CET), postgresql.dialect()
    )
    assert naive == datetime(2026, 9, 24, 12, 0, tzinfo=UTC)
    assert aware == datetime(2026, 9, 24, 13, 0, tzinfo=UTC)
    assert aware is not None and aware.tzinfo is UTC
    assert UTCDateTime().process_result_value(None, sqlite.dialect()) is None
