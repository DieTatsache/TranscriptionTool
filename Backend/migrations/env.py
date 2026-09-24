"""Alembic environment (async engines; SQLite and PostgreSQL)."""

import asyncio
from logging.config import fileConfig
from typing import Any

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

import sonora.models  # noqa: F401  (registers all tables)
from sonora.config import get_settings
from sonora.db import Base
from sonora.db.session import ensure_sqlite_directory
from sonora.db.types import UTCDateTime

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _database_url() -> str:
    # Tests pass the URL via attributes (no configparser %-interpolation issues).
    url = config.attributes.get("database_url")
    return str(url) if url else get_settings().database_url.get_secret_value()


def _render_item(type_: str, obj: Any, _autogen_context: Any) -> str | bool:
    # Keep migrations free of app imports: UTCDateTime is DateTime(timezone=True) in the DB.
    if type_ == "type" and isinstance(obj, UTCDateTime):
        return "sa.DateTime(timezone=True)"
    return False


def _configure(**kwargs: Any) -> None:
    context.configure(
        target_metadata=target_metadata,
        compare_type=True,
        render_item=_render_item,
        **kwargs,
    )


def _run_sync(connection: Connection) -> None:
    # SQLite can't ALTER most things; batch mode rebuilds tables instead.
    _configure(connection=connection, render_as_batch=connection.dialect.name == "sqlite")
    with context.begin_transaction():
        context.run_migrations()


async def _run_online() -> None:
    url = _database_url()
    ensure_sqlite_directory(url)
    # Deliberately without the app's SQLite pragmas: batch table rebuilds must not run
    # with foreign keys enforced, or ON DELETE CASCADE would wipe child rows.
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(_run_sync)
    finally:
        await engine.dispose()


def _run_offline() -> None:
    url = _database_url()
    _configure(url=url, literal_binds=True, render_as_batch=url.startswith("sqlite"))
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    _run_offline()
else:
    asyncio.run(_run_online())
