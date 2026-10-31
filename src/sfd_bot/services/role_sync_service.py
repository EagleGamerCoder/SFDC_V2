"""Discord role operations used after successful account verification."""

from __future__ import annotations

import discord

from sfd_bot.services.verification_service import (
    VerificationRoleNotConfigured,
    VerificationRoleUnavailable,
)


class RoleSyncService:
    """Apply verification-related Discord roles using configured role IDs."""

    def __init__(self, verified_role_id: int | None) -> None:
        self._verified_role_id = verified_role_id

    async def assign_verified_role(self, member: discord.Member) -> bool:
        """Assign the verified role; return False if the member already has it."""
        if self._verified_role_id is None:
            raise VerificationRoleNotConfigured(
                "The verified Discord role has not been configured."
            )

        role = member.guild.get_role(self._verified_role_id)
        if role is None:
            raise VerificationRoleUnavailable(
                "The configured verified role no longer exists in this server."
            )

        if role in member.roles:
            return False

        try:
            await member.add_roles(role, reason="SFD Roblox account verification completed")
        except discord.Forbidden as exc:
            raise VerificationRoleUnavailable(
                "I cannot assign the verified role. Check my Manage Roles permission "
                "and role position."
            ) from exc
        except discord.HTTPException as exc:
            raise VerificationRoleUnavailable(
                "Discord could not assign the verified role. Please contact SFD staff."
            ) from exc

        return True
