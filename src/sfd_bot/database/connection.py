"""Async SQLAlchemy engine and session-factory management."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import logging

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

logger = logging.getLogger(__name__)


class Database:
    """Manage the application's asynchronous database connections.

    This class intentionally does not create tables automatically. Schema changes are
    applied through Alembic migrations so that deployed databases can be upgraded safely.
    """

    def __init__(self, url: str, *, echo: bool = False) -> None:
        self.url = url
        self.engine: AsyncEngine = create_async_engine(
            url,
            echo=echo,
            pool_pre_ping=True,
        )
        if url.startswith("sqlite+aiosqlite://"):
            @event.listens_for(self.engine.sync_engine, "connect")
            def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
                cursor = dbapi_connection.cursor()
                try:
                    cursor.execute("PRAGMA foreign_keys=ON")
                finally:
                    cursor.close()

        self.session_factory = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
        self._disposed = False

    async def check_connection(self) -> None:
        """Run a lightweight query to confirm the database is reachable."""
        async with self.engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        logger.info("Database connection check succeeded.")

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Yield a short-lived session; callers remain responsible for transactions."""
        async with self.session_factory() as session:
            yield session

    async def dispose(self) -> None:
        """Close pooled connections cleanly during application shutdown."""
        if self._disposed:
            return
        await self.engine.dispose()
        self._disposed = True
        logger.info("Database connection pool disposed.")
