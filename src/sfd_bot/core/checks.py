"""Reusable permission checks for slash commands."""

from __future__ import annotations

from collections.abc import Iterable

import discord
from discord import app_commands


def in_guild():
    """Restrict a command to use inside a Discord server, not in DMs."""

    async def predicate(interaction: discord.Interaction) -> bool:
        return interaction.guild is not None

    return app_commands.check(predicate)


def has_any_role_id(*role_ids: int):
    """Require a server member to hold at least one of the supplied role IDs.

    Pass role IDs from validated configuration, not user input. Feature-specific
    services must still re-check permission when performing sensitive operations.
    """
    allowed_ids = frozenset(role_id for role_id in role_ids if role_id > 0)
    if not allowed_ids:
        raise ValueError("At least one positive role ID must be supplied.")

    async def predicate(interaction: discord.Interaction) -> bool:
        member = interaction.user
        if not isinstance(member, discord.Member):
            return False
        member_role_ids = {role.id for role in member.roles}
        return bool(allowed_ids.intersection(member_role_ids))

    return app_commands.check(predicate)


def member_has_any_role(member: discord.Member, role_ids: Iterable[int]) -> bool:
    """Return whether a member has any of the specified role IDs."""
    allowed_ids = set(role_ids)
    return any(role.id in allowed_ids for role in member.roles)