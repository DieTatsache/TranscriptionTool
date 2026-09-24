"""Engine and session factories."""

from pathlib import Path
from typing import Any, cast

from sqlalchemy import CursorResult, Result, event
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def _sqlite_pragmas(dbapi_connection: Any, _record: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")  # off by default in SQLite; needed for cascades
    cursor.execute("PRAGMA journal_mode=WAL")  # readers don't block the writer
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


def ensure_sqlite_directory(url: str) -> None:
    parsed = make_url(url)
    if parsed.get_backend_name() == "sqlite" and parsed.database not in (None, "", ":memory:"):
        Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)


def create_engine(url: str, *, echo: bool = False) -> AsyncEngine:
    if make_url(url).get_backend_name() == "sqlite":
        ensure_sqlite_directory(url)
        engine = create_async_engine(url, echo=echo, connect_args={"timeout": 30})
        event.listen(engine.sync_engine, "connect", _sqlite_pragmas)
        return engine
    return create_async_engine(url, echo=echo, pool_pre_ping=True, pool_size=10, max_overflow=10)


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    # expire_on_commit=False: objects stay usable after commit without implicit (async) reloads.
    return async_sessionmaker(engine, expire_on_commit=False)


def rowcount(result: Result[Any]) -> int:
    """Rows matched by an UPDATE/DELETE (execute() is typed as returning a plain Result)."""
    return cast(CursorResult[Any], result).rowcount
