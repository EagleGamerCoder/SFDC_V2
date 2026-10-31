"""Persistent verification panel and temporary per-user verification controls."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord

from sfd_bot.integrations.roblox.exceptions import RobloxAPIError, RobloxRateLimited
from sfd_bot.services.verification_service import (
    ChallengeExpired,
    ChallengeMismatch,
    ChallengeNotFound,
    ChallengeUnavailable,
    DiscordAlreadyLinked,
    RobloxAlreadyLinked,
    TooManyAttempts,
    VerificationRoleNotConfigured,
    VerificationRoleUnavailable,
)

if TYPE_CHECKING:
    from sfd_bot.bot import DiscordBot

logger = logging.getLogger(__name__)


class VerificationPanelView(discord.ui.View):
    """Persistent public button that starts a private Roblox verification session."""

    def __init__(self, bot: DiscordBot) -> None:
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="Verify with Roblox",
        style=discord.ButtonStyle.success,
        emoji="✅",
        custom_id="sfd:verification:start:v1",
    )
    async def start_verification(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Verification can only be started from the SFD Discord server.",
                ephemeral=True,
            )
            return

        # Import here to avoid a circular import between modal and view modules.
        from sfd_bot.ui.modals import RobloxUsernameModal

        await interaction.response.send_modal(RobloxUsernameModal(self.bot))


class VerificationProgressView(discord.ui.View):
    """Short-lived controls shown privately to the member who started verification."""

    def __init__(
        self,
        bot: SFDDiscordBot,
        *,
        discord_id: int,
        session_id: str,
        timeout_seconds: int,
    ) -> None:
        super().__init__(timeout=float(timeout_seconds))
        self.bot = bot
        self.discord_id = discord_id
        self.session_id = session_id

    async def on_timeout(self) -> None:
        """Cancel the pending challenge when the private controls expire."""
        try:
            await self.bot.verification_service.cancel(
                discord_id=self.discord_id,
                session_id=self.session_id,
            )
        except Exception:
            logger.exception(
                "Could not cancel timed-out verification session for discord_id=%s.",
                self.discord_id,
            )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensure only the member who created the challenge can use its controls."""
        if interaction.user.id != self.discord_id:
            await interaction.response.send_message(
                "This verification session belongs to another Discord member.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(
        label="Check Verification",
        style=discord.ButtonStyle.success,
        emoji="🔎",
        custom_id="sfd:verification:check:temporary",
    )
    async def check_verification(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            outcome = await self.bot.verification_service.check(
                discord_id=self.discord_id,
                session_id=self.session_id,
            )
        except ChallengeMismatch as exc:
            await interaction.followup.send(
                "I haven't found your code in that Roblox profile yet. Make sure the "
                "whole code is in your profile's About / Description section, save the "
                f"change, and try again. **Attempts remaining:** {exc.attempts_remaining}.",
                ephemeral=True,
            )
            return
        except TooManyAttempts:
            await interaction.followup.send(
                "This challenge has been cancelled after too many unsuccessful checks. "
                "Start a new verification from the SFD panel.",
                ephemeral=True,
            )
            self.stop()
            return
        except ChallengeExpired:
            await interaction.followup.send(
                "Your verification code has expired. Start a new verification from the SFD panel.",
                ephemeral=True,
            )
            self.stop()
            return
        except (ChallengeNotFound, ChallengeUnavailable):
            await interaction.followup.send(
                "This verification session is no longer active. "
                "Start a new verification from the SFD panel.",
                ephemeral=True,
            )
            self.stop()
            return
        except (DiscordAlreadyLinked, RobloxAlreadyLinked) as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            self.stop()
            return
        except RobloxRateLimited:
            await interaction.followup.send(
                "Roblox is rate-limiting requests right now. Please wait a little and try again.",
                ephemeral=True,
            )
            return
        except RobloxAPIError:
            logger.exception(
                "Roblox profile check failed for discord_id=%s.",
                self.discord_id,
            )
            await interaction.followup.send(
                "Roblox could not be reached. Your challenge has not been completed; "
                "try again shortly.",
                ephemeral=True,
            )
            return
        except Exception:
            logger.exception(
                "Unexpected verification error for discord_id=%s.",
                self.discord_id,
            )
            await interaction.followup.send(
                "An unexpected error occurred. Please contact SFD staff if it continues.",
                ephemeral=True,
            )
            return

        role_note = ""
        if isinstance(interaction.user, discord.Member):
            try:
                role_added = await self.bot.role_sync_service.assign_verified_role(
                    interaction.user
                )
                role_note = (
                    "Your verified member role has been assigned."
                    if role_added
                    else "You already have the verified member role."
                )
            except (VerificationRoleNotConfigured, VerificationRoleUnavailable):
                logger.exception(
                    "Account verified but verified role could not be assigned; discord_id=%s.",
                    self.discord_id,
                )
                role_note = (
                    "Your Roblox account is verified, but I couldn't assign the Discord role. "
                    "Please contact SFD staff so they can check the role configuration."
                )
        else:
            role_note = (
                "Your Roblox account is verified. Please check your SFD server role assignment."
            )

        success_embed = discord.Embed(
            title="Roblox Account Verified",
            description=(
                f"Your Discord account is now linked to "
                f"[{discord.utils.escape_markdown(outcome.roblox_username)}]"
                f"({outcome.profile_url}).\n\n"
                f"{role_note}"
            ),
            colour=discord.Colour(0x2D9D62),
            timestamp=outcome.verified_at,
        )
        success_embed.set_footer(text="Springfield Fire Department • Verification")

        self.stop()
        try:
            await interaction.edit_original_response(
                content=None,
                embed=success_embed,
                view=None,
            )
        except discord.HTTPException:
            await interaction.followup.send(embed=success_embed, ephemeral=True)

    @discord.ui.button(
        label="Cancel Verification",
        style=discord.ButtonStyle.secondary,
        emoji="✖️",
        custom_id="sfd:verification:cancel:temporary",
    )
    async def cancel_verification(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        cancelled = await self.bot.verification_service.cancel(
            discord_id=self.discord_id,
            session_id=self.session_id,
        )
        self.stop()
        await interaction.response.edit_message(
            content=(
                "Your verification challenge has been cancelled."
                if cancelled
                else "This verification challenge is no longer active."
            ),
            embed=None,
            view=None,
        )
