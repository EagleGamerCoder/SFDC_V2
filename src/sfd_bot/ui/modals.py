"""Discord modals used by SFD interactive workflows."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord

from sfd_bot.integrations.roblox.exceptions import (
    RobloxAPIError,
    RobloxRateLimited,
    RobloxUserNotFound,
)
from sfd_bot.services.verification_service import (
    DiscordAlreadyLinked,
    InvalidRobloxUsername,
    RobloxAlreadyLinked,
)
from sfd_bot.ui.views.verification_view import VerificationProgressView

if TYPE_CHECKING:
    from sfd_bot.bot import DiscordBot

logger = logging.getLogger(__name__)


class RobloxUsernameModal(discord.ui.Modal, title="Roblox Account Verification"):
    """Collect the member's Roblox username before starting a challenge."""

    roblox_username = discord.ui.TextInput(
        label="Roblox username",
        placeholder="Enter your Roblox username (not your display name)",
        min_length=3,
        max_length=20,
        required=True,
    )

    def __init__(self, bot: DiscordBot) -> None:
        super().__init__(timeout=300)
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            challenge = await self.bot.verification_service.start(
                discord_id=interaction.user.id,
                username=str(self.roblox_username.value),
            )
        except InvalidRobloxUsername as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        except RobloxUserNotFound:
            await interaction.followup.send(
                "I couldn't find that Roblox username. Check that you entered your "
                "username rather than your display name, then try again.",
                ephemeral=True,
            )
            return
        except DiscordAlreadyLinked as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        except RobloxAlreadyLinked as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        except RobloxRateLimited:
            await interaction.followup.send(
                "Roblox is receiving too many requests right now. Please try again shortly.",
                ephemeral=True,
            )
            return
        except RobloxAPIError:
            logger.exception("Roblox API failed while starting verification.")
            await interaction.followup.send(
                "Roblox could not be reached. Your verification has not started; "
                "please try again later.",
                ephemeral=True,
            )
            return
        except Exception:
            logger.exception(
                "Unexpected error starting verification for discord_id=%s.",
                interaction.user.id,
            )
            await interaction.followup.send(
                "Something went wrong while starting verification. "
                "Please contact SFD staff if it continues.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="Your Roblox Verification Code",
            description=(
                f"**Roblox account:** [{discord.utils.escape_markdown(challenge.roblox_username)}]"
                f"({challenge.profile_url})\n\n"
                "Add the following code to your Roblox profile's **About / Description** section. "
                "Then return here and press **Check Verification**. You can remove the code "
                "from your profile after verification succeeds."
            ),
            colour=discord.Colour(0xD2A84A),
        )
        embed.add_field(
            name="Temporary code",
            value=f"```text\n{challenge.challenge}\n```",
            inline=False,
        )
        embed.add_field(
            name="Expires",
            value=discord.utils.format_dt(challenge.expires_at, style="R"),
            inline=True,
        )
        embed.add_field(
            name="Attempts",
            value=str(self.bot.settings.verification_max_attempts),
            inline=True,
        )
        embed.set_footer(
            text="Keep this code private. It can only be used for your Discord account."
        )

        view = VerificationProgressView(
            self.bot,
            discord_id=interaction.user.id,
            session_id=challenge.session_id,
            timeout_seconds=self.bot.settings.verification_expiry_minutes * 60,
        )
        await interaction.followup.send(
            embed=embed,
            view=view,
            ephemeral=True,
        )
