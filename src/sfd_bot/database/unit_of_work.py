"""Unit-of-work transaction boundary for repositories sharing one session."""

from __future__ import annotations

from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from sfd_bot.database.connection import Database
from sfd_bot.database.repositories.personnel_repository import PersonnelRepository
from sfd_bot.database.repositories.promotion_repository import PromotionRepository
from sfd_bot.database.repositories.shift_repository import ShiftRepository
from sfd_bot.database.repositories.user_repository import UserRepository
from sfd_bot.database.repositories.verification_session_repository import (
    VerificationSessionRepository,
)


class UnitOfWork:
    """Share one database transaction across related repository operations.

    Usage pattern::

        async with UnitOfWork(database) as uow:
            link = await uow.users.get_by_discord_id(discord_id)
            # perform related writes using other repositories here
            await uow.commit()

    A transaction is not committed automatically. If ``commit`` is not called, the
    unit of work rolls back on exit, including on a normal exit. This helps avoid
    accidentally persisting a partial operation.
    """

    def __init__(self, database: Database) -> None:
        self._session_factory: async_sessionmaker[AsyncSession] = database.session_factory
        self.session: AsyncSession | None = None
        self.users: UserRepository
        self.verification_sessions: VerificationSessionRepository
        self.personnel: PersonnelRepository
        self.promotions: PromotionRepository
        self.shifts: ShiftRepository
        self._committed = False

    async def __aenter__(self) -> UnitOfWork:
        self.session = self._session_factory()
        self.users = UserRepository(self.session)
        self.verification_sessions = VerificationSessionRepository(self.session)
        self.personnel = PersonnelRepository(self.session)
        self.promotions = PromotionRepository(self.session)
        self.shifts = ShiftRepository(self.session)
        self._committed = False
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self.session is None:
            return
        try:
            if exc_type is not None or not self._committed:
                await self.session.rollback()
        finally:
            await self.session.close()
            self.session = None

    async def commit(self) -> None:
        """Commit all writes performed through repositories in this unit of work."""
        if self.session is None:
            raise RuntimeError("UnitOfWork must be entered before commit().")
        await self.session.commit()
        self._committed = True

    async def rollback(self) -> None:
        """Explicitly roll back the current transaction and mark it uncommitted."""
        if self.session is None:
            raise RuntimeError("UnitOfWork must be entered before rollback().")
        await self.session.rollback()
        self._committed = False

    def require_session(self) -> AsyncSession:
        """Return the active session or fail clearly if used outside the context."""
        if self.session is None:
            raise RuntimeError("UnitOfWork is not active. Use it inside 'async with'.")
        return self.session
