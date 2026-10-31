"""Application service for SFD apparatus and radio callsign allocation."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.exc import IntegrityError

from sfd_bot.core.json_loader import load_json_object
from sfd_bot.database.connection import Database
from sfd_bot.database.models import ApparatusAssignment, ApparatusUnit, AuditEvent, utc_now
from sfd_bot.database.unit_of_work import UnitOfWork

logger = logging.getLogger(__name__)


class CallsignError(Exception):
    """Base class for expected callsign-management errors."""


class CallsignUnitNotFound(CallsignError):
    """The requested apparatus does not exist or is disabled."""


class CallsignNotVerified(CallsignError):
    """The member has not linked a Roblox account."""


class CallsignPersonnelInactive(CallsignError):
    """An existing personnel record is not active."""


class CallsignWrongDivision(CallsignError):
    """The member's recorded division does not match the selected unit."""


class CallsignAlreadyAssigned(CallsignError):
    """The member already has an active callsign."""


class CallsignNotAssigned(CallsignError):
    """The member does not currently have an active callsign."""


class CallsignNoPositionsAvailable(CallsignError):
    """The selected unit has no unoccupied crew positions."""


class CallsignInvalidPosition(CallsignError):
    """The requested position is not configured for the selected unit."""


class CallsignPositionTaken(CallsignError):
    """Another member took the selected position before the assignment completed."""


class CallsignCommandUnitRestricted(CallsignError):
    """A named command callsign must be assigned by department management."""


@dataclass(frozen=True, slots=True)
class CallsignAssignmentInfo:
    assignment_id: int
    guild_id: int
    discord_id: int
    apparatus_code: str
    apparatus_name: str
    division_key: str
    callsign: str
    position_number: int
    position_key: str
    position_label: str
    assigned_at: datetime
    assigned_by_discord_id: int | None


@dataclass(frozen=True, slots=True)
class ApparatusRosterInfo:
    code: str
    name: str
    division_key: str
    self_assignable: bool
    positions: tuple[dict[str, Any], ...]
    assignments: tuple[CallsignAssignmentInfo, ...]


class CallsignService:
    """Allocate and release callsigns without exposing SQLAlchemy to Discord cogs."""

    def __init__(self, database: Database, definitions_path: Path) -> None:
        self._database = database
        self._definitions = self._load_definitions(definitions_path)

    @staticmethod
    def _load_definitions(path: Path) -> tuple[dict[str, Any], ...]:
        data = load_json_object(path)
        raw_units = data.get("units")
        if not isinstance(raw_units, list) or not raw_units:
            raise ValueError("apparatus.json must contain a non-empty 'units' list.")

        definitions: list[dict[str, Any]] = []
        seen_codes: set[str] = set()
        for raw in raw_units:
            if not isinstance(raw, dict):
                raise ValueError("Every apparatus definition must be an object.")
            code = str(raw.get("code", "")).strip()
            name = str(raw.get("name", "")).strip()
            division_key = str(raw.get("division_key", "")).strip().lower()
            positions = raw.get("positions")
            if (
                not code
                or not name
                or not division_key
                or not isinstance(positions, list)
                or not positions
            ):
                raise ValueError(f"Invalid apparatus definition for code {code!r}.")
            if code in seen_codes:
                raise ValueError(f"Duplicate apparatus code {code!r} in {path}.")
            seen_codes.add(code)

            normalised_positions: list[dict[str, Any]] = []
            seen_positions: set[int] = set()
            for position in positions:
                if not isinstance(position, dict):
                    raise ValueError(f"Positions for apparatus {code} must be objects.")
                number = position.get("number")
                key = str(position.get("key", "")).strip()
                label = str(position.get("label", "")).strip()
                callsign = str(position.get("callsign", "")).strip()
                self_assignable = bool(position.get("self_assignable", True))
                if not isinstance(number, int) or number < 1 or not key or not label:
                    raise ValueError(f"Invalid position in apparatus {code}.")
                if number in seen_positions:
                    raise ValueError(f"Duplicate position {number} in apparatus {code}.")
                seen_positions.add(number)
                normalised_positions.append(
                    {
                        "number": number,
                        "key": key,
                        "label": label,
                        "callsign": callsign,
                        "self_assignable": self_assignable,
                    }
                )

            definitions.append(
                {
                    "code": code,
                    "name": name,
                    "division_key": division_key,
                    "self_assignable": bool(raw.get("self_assignable", True)),
                    "sort_order": int(raw.get("sort_order", 100)),
                    "positions": normalised_positions,
                }
            )

        return tuple(definitions)

    async def setup_guild(self, guild_id: int) -> int:
        """Insert configured apparatus that does not yet exist for the guild.

        Existing rows are deliberately left untouched, so changing the JSON file does
        not silently overwrite a guild's database configuration.
        """
        try:
            async with UnitOfWork(self._database) as uow:
                existing_units = await uow.apparatus.list_units(
                    guild_id,
                    enabled_only=False,
                )
                existing = {unit.code for unit in existing_units}
                created = 0
                for definition in self._definitions:
                    if definition["code"] in existing:
                        continue
                    await uow.apparatus.create_unit(
                        guild_id=guild_id,
                        code=definition["code"],
                        name=definition["name"],
                        division_key=definition["division_key"],
                        positions=definition["positions"],
                        self_assignable=definition["self_assignable"],
                        sort_order=definition["sort_order"],
                    )
                    created += 1
                if created:
                    await uow.commit()
                    logger.info(
                        "Created %s default apparatus record(s) for guild_id=%s.",
                        created,
                        guild_id,
                    )
                return created
        except IntegrityError:
            # Two first-time interactions may initialise the guild concurrently. A
            # unique guild/code constraint makes the seed idempotent; re-read once.
            async with UnitOfWork(self._database) as uow:
                existing_units = await uow.apparatus.list_units(
                    guild_id,
                    enabled_only=False,
                )
                existing = {unit.code for unit in existing_units}
                missing = {item["code"] for item in self._definitions} - existing
                if missing:
                    raise
                return 0

    async def list_units(self, guild_id: int) -> list[ApparatusUnit]:
        await self.setup_guild(guild_id)
        async with UnitOfWork(self._database) as uow:
            return await uow.apparatus.list_units(guild_id)

    async def take_next(
        self,
        *,
        guild_id: int,
        discord_id: int,
        unit_code: str,
    ) -> CallsignAssignmentInfo:
        """Give a verified member the first available position in a self-service unit."""
        return await self._assign(
            guild_id=guild_id,
            discord_id=discord_id,
            unit_code=unit_code,
            actor_id=discord_id,
            position_number=None,
            allow_command_unit=False,
        )

    async def assign(
        self,
        *,
        guild_id: int,
        discord_id: int,
        unit_code: str,
        actor_id: int,
        position_number: int | None = None,
    ) -> CallsignAssignmentInfo:
        """Allow an authorised supervisor to assign a specific member."""
        return await self._assign(
            guild_id=guild_id,
            discord_id=discord_id,
            unit_code=unit_code,
            actor_id=actor_id,
            position_number=position_number,
            allow_command_unit=True,
        )

    async def _assign(
        self,
        *,
        guild_id: int,
        discord_id: int,
        unit_code: str,
        actor_id: int,
        position_number: int | None,
        allow_command_unit: bool,
    ) -> CallsignAssignmentInfo:
        await self.setup_guild(guild_id)
        try:
            async with UnitOfWork(self._database) as uow:
                unit = await uow.apparatus.get_unit_by_code(guild_id, unit_code)
                if unit is None or not unit.is_enabled:
                    raise CallsignUnitNotFound(
                        f"Apparatus {unit_code} is not configured or enabled."
                    )
                if not allow_command_unit and not unit.self_assignable:
                    raise CallsignCommandUnitRestricted(
                        "Named command callsigns can only be assigned by department management."
                    )

                await self._check_member_eligibility(uow, guild_id, discord_id, unit.division_key)
                existing = await uow.apparatus.get_active_for_member(
                    guild_id=guild_id,
                    discord_id=discord_id,
                )
                if existing is not None:
                    raise CallsignAlreadyAssigned(
                        f"You already have **{existing[0].callsign}** assigned to "
                        f"{existing[1].name}. "
                        "Release it or ask a supervisor to transfer you."
                    )

                assignment = await self._create_assignment(
                    uow=uow,
                    guild_id=guild_id,
                    discord_id=discord_id,
                    unit=unit,
                    actor_id=actor_id,
                    position_number=position_number,
                    allow_reserved_position=allow_command_unit,
                )
                self._add_audit(
                    uow,
                    guild_id=guild_id,
                    actor_id=actor_id,
                    target_id=discord_id,
                    event_type="callsign_assigned",
                    details={
                        "callsign": assignment.callsign,
                        "apparatus": unit.code,
                        "unit_name": unit.name,
                    },
                )
                await uow.commit()
                return self._to_info(assignment, unit)
        except IntegrityError as exc:
            raise CallsignPositionTaken(
                "That crew position was just assigned to someone else. Please try again."
            ) from exc

    async def transfer(
        self,
        *,
        guild_id: int,
        discord_id: int,
        unit_code: str,
        actor_id: int,
        position_number: int | None = None,
    ) -> CallsignAssignmentInfo:
        """Atomically release a member's current callsign and assign a new one."""
        await self.setup_guild(guild_id)
        try:
            async with UnitOfWork(self._database) as uow:
                current = await uow.apparatus.get_active_for_member(
                    guild_id=guild_id,
                    discord_id=discord_id,
                )
                if current is None:
                    raise CallsignNotAssigned(
                        "That member does not have an active callsign to transfer."
                    )

                unit = await uow.apparatus.get_unit_by_code(guild_id, unit_code)
                if unit is None or not unit.is_enabled:
                    raise CallsignUnitNotFound(
                        f"Apparatus {unit_code} is not configured or enabled."
                    )
                await self._check_member_eligibility(uow, guild_id, discord_id, unit.division_key)

                old_assignment, old_unit = current
                old_assignment.status = "released"
                old_assignment.released_at = utc_now()
                await uow.session.flush()

                assignment = await self._create_assignment(
                    uow=uow,
                    guild_id=guild_id,
                    discord_id=discord_id,
                    unit=unit,
                    actor_id=actor_id,
                    position_number=position_number,
                    allow_reserved_position=True,
                )
                self._add_audit(
                    uow,
                    guild_id=guild_id,
                    actor_id=actor_id,
                    target_id=discord_id,
                    event_type="callsign_transferred",
                    details={
                        "old_callsign": old_assignment.callsign,
                        "old_unit": old_unit.code,
                        "new_callsign": assignment.callsign,
                        "new_unit": unit.code,
                    },
                )
                await uow.commit()
                return self._to_info(assignment, unit)
        except IntegrityError as exc:
            raise CallsignPositionTaken(
                "The requested crew position is no longer available. No transfer was made."
            ) from exc

    async def release(
        self,
        *,
        guild_id: int,
        discord_id: int,
        actor_id: int,
    ) -> CallsignAssignmentInfo:
        """Release a member's active callsign and preserve the assignment history."""
        async with UnitOfWork(self._database) as uow:
            current = await uow.apparatus.release_active_for_member(
                guild_id=guild_id,
                discord_id=discord_id,
            )
            if current is None:
                raise CallsignNotAssigned("That member does not currently have a callsign.")
            assignment, unit = current
            self._add_audit(
                uow,
                guild_id=guild_id,
                actor_id=actor_id,
                target_id=discord_id,
                event_type="callsign_released",
                details={
                    "callsign": assignment.callsign,
                    "apparatus": unit.code,
                    "unit_name": unit.name,
                },
            )
            await uow.commit()
            return self._to_info(assignment, unit)

    async def get_member_assignment(
        self,
        *,
        guild_id: int,
        discord_id: int,
    ) -> CallsignAssignmentInfo | None:
        async with UnitOfWork(self._database) as uow:
            current = await uow.apparatus.get_active_for_member(
                guild_id=guild_id,
                discord_id=discord_id,
            )
            if current is None:
                return None
            return self._to_info(current[0], current[1])

    async def get_roster(self, guild_id: int) -> list[ApparatusRosterInfo]:
        await self.setup_guild(guild_id)
        async with UnitOfWork(self._database) as uow:
            units = await uow.apparatus.list_units(guild_id)
            active = await uow.apparatus.list_active_for_guild(guild_id)
            by_unit: dict[int, list[CallsignAssignmentInfo]] = {}
            for assignment, unit in active:
                by_unit.setdefault(unit.id, []).append(self._to_info(assignment, unit))
            return [
                ApparatusRosterInfo(
                    code=unit.code,
                    name=unit.name,
                    division_key=unit.division_key,
                    self_assignable=unit.self_assignable,
                    positions=tuple(unit.positions),
                    assignments=tuple(by_unit.get(unit.id, [])),
                )
                for unit in units
            ]

    async def release_for_shift_end(
        self,
        *,
        guild_id: int,
        discord_id: int,
        actor_id: int,
    ) -> CallsignAssignmentInfo | None:
        """Integration hook for the future shift service's off-duty operation."""
        current = await self.get_member_assignment(guild_id=guild_id, discord_id=discord_id)
        if current is None:
            return None
        return await self.release(guild_id=guild_id, discord_id=discord_id, actor_id=actor_id)

    async def _check_member_eligibility(
        self,
        uow: UnitOfWork,
        guild_id: int,
        discord_id: int,
        division_key: str,
    ) -> None:
        if await uow.users.get_by_discord_id(discord_id) is None:
            raise CallsignNotVerified(
                "That member must complete SFD Roblox verification before receiving a callsign."
            )
        personnel = await uow.personnel.get_for_member(guild_id, discord_id)
        if personnel is not None:
            if personnel.status != "active":
                raise CallsignPersonnelInactive(
                    "That member's SFD personnel record is not active."
                )
            if personnel.division_key and division_key not in {"command", personnel.division_key}:
                raise CallsignWrongDivision(
                    f"That member is assigned to **{personnel.division_key.upper()}**, "
                    f"not **{division_key.upper()}**."
                )

    async def _create_assignment(
        self,
        *,
        uow: UnitOfWork,
        guild_id: int,
        discord_id: int,
        unit: ApparatusUnit,
        actor_id: int,
        position_number: int | None,
        allow_reserved_position: bool,
    ) -> ApparatusAssignment:
        positions = unit.positions
        if not isinstance(positions, list) or not positions:
            raise CallsignNoPositionsAvailable(f"{unit.name} has no configured crew positions.")

        if position_number is None:
            if not unit.self_assignable:
                raise CallsignCommandUnitRestricted(
                    "A manager must select the specific named command position."
                )
            occupied = {
                item.position_number
                for item in await uow.apparatus.list_active_for_unit(
                    guild_id=guild_id,
                    apparatus_id=unit.id,
                )
            }
            available = [
                item
                for item in positions
                if isinstance(item, dict)
                and item.get("number") not in occupied
                and item.get("self_assignable", True)
            ]
            if not available:
                raise CallsignNoPositionsAvailable(
                    f"There are no available positions on {unit.name}."
                )
            selected = min(available, key=lambda item: int(item["number"]))
        else:
            selected = next(
                (
                    item for item in positions
                    if isinstance(item, dict) and item.get("number") == position_number
                ),
                None,
            )
            if selected is not None and not allow_reserved_position:
                if not selected.get("self_assignable", True):
                    raise CallsignInvalidPosition(
                        "That position is reserved for assignment by SFD management."
                    )
            if selected is None:
                valid_positions = [
                    str(item.get("number"))
                    for item in positions
                    if isinstance(item, dict)
                ]
                valid = ", ".join(valid_positions)
                raise CallsignInvalidPosition(
                    f"Position {position_number} is not configured for {unit.name}. "
                    f"Available positions: {valid}."
                )
            occupied = {
                item.position_number
                for item in await uow.apparatus.list_active_for_unit(
                    guild_id=guild_id,
                    apparatus_id=unit.id,
                )
            }
            if position_number in occupied:
                raise CallsignPositionTaken(
                    f"Position {position_number} on {unit.name} is already occupied."
                )

        number = int(selected["number"])
        callsign = str(selected.get("callsign") or f"{unit.code}-{number}")
        return await uow.apparatus.create_assignment(
            guild_id=guild_id,
            apparatus_id=unit.id,
            discord_id=discord_id,
            callsign=callsign,
            position_number=number,
            position_key=str(selected["key"]),
            position_label=str(selected["label"]),
            assigned_by_discord_id=actor_id,
        )

    @staticmethod
    def _add_audit(
        uow: UnitOfWork,
        *,
        guild_id: int,
        actor_id: int,
        target_id: int,
        event_type: str,
        details: dict[str, Any],
    ) -> None:
        session = uow.require_session()
        session.add(
            AuditEvent(
                guild_id=guild_id,
                event_type=event_type,
                actor_discord_id=actor_id,
                target_discord_id=target_id,
                details=details,
            )
        )

    @staticmethod
    def _to_info(assignment: ApparatusAssignment, unit: ApparatusUnit) -> CallsignAssignmentInfo:
        return CallsignAssignmentInfo(
            assignment_id=assignment.id,
            guild_id=assignment.guild_id,
            discord_id=assignment.discord_id,
            apparatus_code=unit.code,
            apparatus_name=unit.name,
            division_key=unit.division_key,
            callsign=assignment.callsign,
            position_number=assignment.position_number,
            position_key=assignment.position_key,
            position_label=assignment.position_label,
            assigned_at=assignment.assigned_at,
            assigned_by_discord_id=assignment.assigned_by_discord_id,
        )
