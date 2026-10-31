"""Alembic environment using the application's asynchronous SQLAlchemy URL."""

from __future__ import annotations

import asyncio
from logging.config import fileConfig
import os
from pathlib import Path

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from sfd_bot.database.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env", override=False)

database_url = os.getenv("DATABASE_URL", "").strip()
if not database_url:
    default_path = (PROJECT_ROOT / "data" / "sfd_bot.db").as_posix()
    database_url = f"sqlite+aiosqlite:///{default_path}"
if not database_url.startswith(("sqlite+aiosqlite://", "postgresql+asyncpg://")):
    raise RuntimeError(
        "DATABASE_URL must use sqlite+aiosqlite:// or postgresql+asyncpg:// for migrations."
    )
# Escape percent signs for ConfigParser (e.g. encoded characters in hosted DB passwords).
config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations without opening a database connection."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_as_batch=config.get_main_option("sqlalchemy.url").startswith("sqlite+aiosqlite://"),
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    """Apply migrations on a synchronous connection supplied by the async engine."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        render_as_batch=connection.dialect.name == "sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine and run migrations through Alembic's sync bridge."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    try:
        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)
    finally:
        await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
