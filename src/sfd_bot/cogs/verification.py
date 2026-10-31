"""Discord commands for SFD Roblox account verification."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from sfd_bot.ui.embeds import create_verification_panel
from sfd_bot.ui.views.verification_view import VerificationPanelView

if TYPE_CHECKING:
    from sfd_bot.bot import DiscordBot

logger = logging.getLogger(__name__)


class Verification(commands.Cog):
    """Publish and manage the member-facing Roblox verification workflow."""

    def __init__(self, bot: DiscordBot) -> None:
        self.bot = bot

    @app_commands.command(
        name="verification-panel",
        description="Publish the SFD Roblox account verification panel.",
    )
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    async def verification_panel(self, interaction: discord.Interaction) -> None:
        """Post the persistent verification embed in the current channel."""
        channel = interaction.channel
        if channel is None or not hasattr(channel, "send"):
            await interaction.response.send_message(
                "I can't publish a verification panel in this channel.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        embed, files = create_verification_panel()
        try:
            message = await channel.send(
                embed=embed,
                files=files,
                view=VerificationPanelView(self.bot),
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "I don't have permission to send messages or attach files in this channel.",
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            logger.exception("Failed to publish SFD verification panel.")
            await interaction.followup.send(
                "Discord couldn't publish the verification panel. Please try again.",
                ephemeral=True,
            )
            return

        logger.info(
            "Verification panel published by discord_id=%s in channel_id=%s message_id=%s.",
            interaction.user.id,
            channel.id,
            message.id,
        )
        await interaction.followup.send(
            f"The SFD verification panel has been published in {channel.mention}.",
            ephemeral=True,
        )

    @app_commands.command(
        name="verify-status",
        description="Check whether your Roblox account is linked to your Discord account.",
    )
    async def verify_status(self, interaction: discord.Interaction) -> None:
        """Display the caller's current account-link status privately."""
        account = await self.bot.verification_service.get_link(interaction.user.id)
        if account is None:
            embed = discord.Embed(
                title="Roblox Verification Status",
                description=(
                    "Your Discord account is not currently linked to a Roblox account. "
                    "Use the SFD verification panel to get started."
                ),
                colour=discord.Colour(0xD2A84A),
            )
        else:
            embed = discord.Embed(
                title="Roblox Verification Status",
                description="Your Roblox account is successfully linked.",
                colour=discord.Colour(0x2D9D62),
            )
            embed.add_field(
                name="Roblox Username",
                value=f"[{discord.utils.escape_markdown(account.roblox_username)}]"
                f"(https://www.roblox.com/users/{account.roblox_user_id}/profile)",
                inline=True,
            )
            embed.add_field(
                name="Roblox User ID",
                value=f"`{account.roblox_user_id}`",
                inline=True,
            )
            embed.add_field(
                name="Verified",
                value=discord.utils.format_dt(account.verified_at, style="F"),
                inline=False,
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @verification_panel.error
    async def verification_panel_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            message = "You need the **Manage Server** permission to publish the verification panel."
        else:
            logger.error(
                "Verification panel command failed.",
                exc_info=(type(error), error, error.__traceback__),
            )
            message = "The verification panel command failed. Please contact a bot administrator."

        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    """Load the verification cog as a Discord extension."""
    await bot.add_cog(Verification(bot))
