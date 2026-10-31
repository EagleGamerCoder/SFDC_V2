"""Repository for SFD apparatus units and callsign assignments."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sfd_bot.database.models import ApparatusAssignment, ApparatusUnit, utc_now


class ApparatusRepository:
    """Read and write apparatus and assignments within the caller's transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_units(self, guild_id: int, *, enabled_only: bool = True) -> list[ApparatusUnit]:
        statement = select(ApparatusUnit).where(ApparatusUnit.guild_id == guild_id)
        if enabled_only:
            statement = statement.where(ApparatusUnit.is_enabled.is_(True))
        result = await self._session.execute(
            statement.order_by(ApparatusUnit.sort_order, ApparatusUnit.code)
        )
        return list(result.scalars().all())

    async def get_unit_by_code(self, guild_id: int, code: str) -> ApparatusUnit | None:
        result = await self._session.execute(
            select(ApparatusUnit).where(
                ApparatusUnit.guild_id == guild_id,
                ApparatusUnit.code == code,
            )
        )
        return result.scalar_one_or_none()

    async def create_unit(
        self,
        *,
        guild_id: int,
        code: str,
        name: str,
        division_key: str,
        positions: list[dict[str, Any]],
        self_assignable: bool,
        sort_order: int,
    ) -> ApparatusUnit:
        unit = ApparatusUnit(
            guild_id=guild_id,
            code=code,
            name=name,
            division_key=division_key,
            positions=positions,
            self_assignable=self_assignable,
            is_enabled=True,
            sort_order=sort_order,
        )
        self._session.add(unit)
        await self._session.flush()
        return unit

    async def get_active_for_member(
        self,
        *,
        guild_id: int,
        discord_id: int,
    ) -> tuple[ApparatusAssignment, ApparatusUnit] | None:
        result = await self._session.execute(
            select(ApparatusAssignment, ApparatusUnit)
            .join(ApparatusUnit, ApparatusUnit.id == ApparatusAssignment.apparatus_id)
            .where(
                ApparatusAssignment.guild_id == guild_id,
                ApparatusAssignment.discord_id == discord_id,
                ApparatusAssignment.status == "active",
            )
        )
        row = result.first()
        return (row[0], row[1]) if row is not None else None

    async def list_active_for_unit(
        self,
        *,
        guild_id: int,
        apparatus_id: int,
    ) -> list[ApparatusAssignment]:
        result = await self._session.execute(
            select(ApparatusAssignment)
            .where(
                ApparatusAssignment.guild_id == guild_id,
                ApparatusAssignment.apparatus_id == apparatus_id,
                ApparatusAssignment.status == "active",
            )
            .order_by(ApparatusAssignment.position_number)
        )
        return list(result.scalars().all())

    async def list_active_for_guild(
        self,
        guild_id: int,
    ) -> list[tuple[ApparatusAssignment, ApparatusUnit]]:
        result = await self._session.execute(
            select(ApparatusAssignment, ApparatusUnit)
            .join(ApparatusUnit, ApparatusUnit.id == ApparatusAssignment.apparatus_id)
            .where(
                ApparatusAssignment.guild_id == guild_id,
                ApparatusAssignment.status == "active",
            )
            .order_by(
                ApparatusUnit.sort_order,
                ApparatusUnit.code,
                ApparatusAssignment.position_number,
            )
        )
        return [(row[0], row[1]) for row in result.all()]

    async def create_assignment(
        self,
        *,
        guild_id: int,
        apparatus_id: int,
        discord_id: int,
        callsign: str,
        position_number: int,
        position_key: str,
        position_label: str,
        assigned_by_discord_id: int | None,
        assigned_at: datetime | None = None,
    ) -> ApparatusAssignment:
        assignment = ApparatusAssignment(
            guild_id=guild_id,
            apparatus_id=apparatus_id,
            discord_id=discord_id,
            callsign=callsign,
            position_number=position_number,
            position_key=position_key,
            position_label=position_label,
            status="active",
            assigned_by_discord_id=assigned_by_discord_id,
            assigned_at=assigned_at or utc_now(),
        )
        self._session.add(assignment)
        await self._session.flush()
        return assignment

    async def release_active_for_member(
        self,
        *,
        guild_id: int,
        discord_id: int,
        released_at: datetime | None = None,
    ) -> tuple[ApparatusAssignment, ApparatusUnit] | None:
        current = await self.get_active_for_member(guild_id=guild_id, discord_id=discord_id)
        if current is None:
            return None
        assignment, unit = current
        assignment.status = "released"
        assignment.released_at = released_at or utc_now()
        await self._session.flush()
        return assignment, unit

    async def list_history_for_member(
        self,
        *,
        guild_id: int,
        discord_id: int,
        limit: int = 10,
    ) -> list[tuple[ApparatusAssignment, ApparatusUnit]]:
        result = await self._session.execute(
            select(ApparatusAssignment, ApparatusUnit)
            .join(ApparatusUnit, ApparatusUnit.id == ApparatusAssignment.apparatus_id)
            .where(
                ApparatusAssignment.guild_id == guild_id,
                ApparatusAssignment.discord_id == discord_id,
            )
            .order_by(ApparatusAssignment.assigned_at.desc())
            .limit(max(1, min(limit, 50)))
        )
        return [(row[0], row[1]) for row in result.all()]
