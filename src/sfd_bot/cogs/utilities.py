"""Basic slash commands used to verify that the bot foundation is running."""

from __future__ import annotations

from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from sfd_bot import __version__
from sfd_bot.core.constants import APP_NAME, SFD_GOLD, SFD_RED
from sfd_bot.ui.embeds import create_sfd_embed

class Utilities(commands.Cog):
    """General, non-sensitive commands available to SFD server members."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="ping", description="Check whether the SFD bot is responding.")
    async def ping(self, interaction: discord.Interaction) -> None:
        """Report approximate Discord gateway latency."""

        latency_ms = round(self.bot.latency * 1000)

        embed, files = create_sfd_embed(
            title="SFD Systems Status",
            description=(
                "Pong."
            ),
            footer=f"SFD Dispatch • v{__version__}",
        )
        embed.add_field(
            name="System Status",
            value="🟢 Operational",
            inline=True,
        )
        embed.add_field(
            name="Gateway Latency",
            value=f"`{latency_ms} ms`",
            inline=True,
        )
        embed.add_field(
            name="Connection",
            value="Discord Gateway",
            inline=True,
        )
        await interaction.response.send_message(
            embed=embed,
            files=files,
            ephemeral=True,
        )

    @app_commands.command(name="botinfo", description="Display basic information about the SFD bot.")
    async def botinfo(self, interaction: discord.Interaction) -> None:
        """Display safe runtime details for troubleshooting."""

        embed, files = create_sfd_embed(
            title="SFD Dispatch",
            description=(
                "Department systems and server tools "
                "for Springfield Fire Department."
            ),
            footer=f"Bot Information • v{__version__}",
        )
        embed.add_field(
            name="Application Version",
            value=f"`{__version__}`",
            inline=True,
        )
        embed.add_field(
            name="Discord.py",
            value=f"`{discord.__version__}`",
            inline=True,
        )
        embed.add_field(
            name="Connected Servers",
            value=f"`{len(self.bot.guilds)}`",
            inline=True,
        )
        embed.add_field(
            name="Gateway Latency",
            value=f"`{round(self.bot.latency * 1000)} ms`",
            inline=True,
        )
        await interaction.response.send_message(
            embed=embed,
            files=files,
            ephemeral=True,
        )

    @app_commands.command(name="serverinfo", description="Display basic information about this server.")
    @app_commands.guild_only()
    async def serverinfo(self, interaction: discord.Interaction) -> None:
        """Show basic information about the current Discord guild."""

        guild = interaction.guild

        if guild is None:
            await interaction.response.send_message(
                "This command can only be used inside a Discord server.",
                ephemeral=True,
            )
            return

        embed, files = create_sfd_embed(
            title=guild.name,
            description=(
                "Springfield Fire Department Discord server "
                "information."
            ),
            footer=f"SFD Server Information • v{__version__}",
        )
        embed.add_field(
            name="Server ID",
            value=f"`{guild.id}`",
            inline=True,
        )
        embed.add_field(
            name="Created",
            value=discord.utils.format_dt(
                guild.created_at,
                style="D",
            ),
            inline=True,
        )
        embed.add_field(
            name="Member Count",
            value=f"`{guild.member_count or 0}`",
            inline=True,
        )
        if guild.icon is not None:
            embed.set_thumbnail(url=guild.icon.url)
        await interaction.response.send_message(
            embed=embed,
            files=files,
            ephemeral=True,
        )

async def setup(bot: commands.Bot) -> None:
    """Load this cog as a discord.py extension."""
    await bot.add_cog(Utilities(bot))
