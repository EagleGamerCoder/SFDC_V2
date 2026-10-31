"""Discord commands for SFD callsign and apparatus management.

This cog deliberately uses ordinary Discord interactions and bot messages only. It does
not create Discord webhooks or receive external dispatch webhooks.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from sfd_bot.services.callsign_service import (
    ApparatusRosterInfo,
    CallsignError,
    CallsignNotAssigned,
)
from sfd_bot.ui.embeds import create_sfd_embed

if TYPE_CHECKING:
    from sfd_bot.bot import DiscordBot

logger = logging.getLogger(__name__)

TAKE_UNIT_CHOICES = [
    app_commands.Choice(name="21 • Engine 2 (ERD)", value="21"),
    app_commands.Choice(name="22 • Ladder 2 (ERD)", value="22"),
    app_commands.Choice(name="23 • Medic 2 (EMSD)", value="23"),
    app_commands.Choice(name="24 • Brush 2 (FSD)", value="24"),
    app_commands.Choice(name="25 • Training 2 (TAAD)", value="25"),
]

ALL_UNIT_CHOICES = [
    app_commands.Choice(name="20 • Command 2 (Command staff only)", value="20"),
    *TAKE_UNIT_CHOICES,
]

class Callsigns(commands.Cog):
    """Allocate, transfer, release and display SFD callsigns."""

    callsign = app_commands.Group(
        name="callsign",
        description="SFD apparatus assignments and radio callsigns.",
    )

    def __init__(self, bot: DiscordBot) -> None:
        self.bot = bot

    def _has_personnel_role(self, member: discord.Member) -> bool:
        """Check the configured Fire Department Personnel role.

        If SFD_PERSONNEL_ROLE_ID is not configured, use the exact role name as a
        migration-friendly fallback. Configure the ID for production use.
        """
        configured_role_id = self.bot.settings.personnel_role_id
        if configured_role_id is not None:
            return any(role.id == configured_role_id for role in member.roles)
        return any(role.name.casefold() == "Fire Department Personnel" for role in member.roles)

    async def _require_personnel(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
    ) -> bool:
        if self._has_personnel_role(member):
            return True

        if self.bot.settings.personnel_role_id is None:
            message = (
                'You need the **Fire Department Personnel** role. Create that role or set '
                '`SFD_PERSONNEL_ROLE_ID` in your `.env` file to its ID.'
            )
        else:
            message = (
                "You need the configured **Fire Department Personnel** role "
                "to receive a callsign."
            )

        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
        return False

    @staticmethod
    def _assignment_embed(
        *,
        title: str,
        description: str,
        callsign: str,
        unit_name: str,
        position_label: str,
        member_id: int,
    ) -> tuple[discord.Embed, list[discord.File]]:
        embed, files = create_sfd_embed(
            title=title,
            description=description,
            footer="SFD Command • Apparatus Management",
        )
        embed.add_field(name="Assigned Member", value=f"<@{member_id}>", inline=True)
        embed.add_field(name="Callsign", value=f"`{callsign}`", inline=True)
        embed.add_field(name="Apparatus", value=unit_name, inline=True)
        embed.add_field(name="Crew Position", value=position_label, inline=False)
        return embed, files

    @staticmethod
    def _roster_embed(
        roster: list[ApparatusRosterInfo],
        *,
        title: str = "SFD Apparatus Roster",
    ) -> tuple[discord.Embed, list[discord.File]]:
        assigned_total = sum(len(unit.assignments) for unit in roster)
        unit_total = len(roster)
        active_units = sum(bool(unit.assignments) for unit in roster)

        embed, files = create_sfd_embed(
            title=title,
            description=(
                "Current Station 2 apparatus and personnel assignments.\n"
                "Members can use `/callsign take` to receive the next available crew position."
            ),
            footer="SFD Command • Apparatus Management",
        )
        embed.add_field(name="Assigned Personnel", value=f"`{assigned_total}`", inline=True)
        embed.add_field(name="Units with Crew", value=f"`{active_units}/{unit_total}`", inline=True)
        embed.add_field(name="Station", value="`Station 2`", inline=True)

        for unit in roster:
            assigned_by_position = {
                assignment.position_number: assignment for assignment in unit.assignments
            }
            lines: list[str] = []
            for position in unit.positions:
                number = int(position["number"])
                callsign_value = str(position.get("callsign") or f"{unit.code}-{number}")
                assignment = assigned_by_position.get(number)
                if assignment is None:
                    if position.get("self_assignable", True):
                        availability = "Available"
                    else:
                        availability = "Reserved for management"
                    lines.append(
                        f"`{callsign_value}` · **{availability}** — {position['label']}"
                    )
                else:
                    lines.append(
                        f"`{assignment.callsign}` · <@{assignment.discord_id}> — "
                        f"{assignment.position_label}"
                    )

            division = unit.division_key.upper()
            embed.add_field(
                name=f"{unit.code} • {unit.name}  |  {division}",
                value="\n".join(lines) or "No crew positions configured.",
                inline=False,
            )

        return embed, files

    @callsign.command(
        name="setup",
        description="Initialise the default SFD apparatus and callsign list for this server.",
    )
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setup_apparatus(self, interaction: discord.Interaction) -> None:
        """Create missing default apparatus records without overwriting existing records."""
        if interaction.guild is None:
            await interaction.response.send_message(
                "This command must be used in a server.",
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        created = await self.bot.callsign_service.setup_guild(interaction.guild.id)
        embed, files = create_sfd_embed(
            title="SFD Callsign Configuration",
            description=(
                f"Apparatus configuration is ready for **{interaction.guild.name}**.\n"
                f"Created **{created}** missing apparatus record(s). "
                "Existing records were not changed."
            ),
            footer="SFD Command • Apparatus Management",
        )
        await interaction.followup.send(embed=embed, files=files, ephemeral=True)

    @callsign.command(
        name="take",
        description="Automatically receive the next available callsign on an apparatus.",
    )
    @app_commands.guild_only()
    @app_commands.describe(unit="Choose the apparatus you are joining.")
    @app_commands.choices(unit=TAKE_UNIT_CHOICES)
    async def take(self, interaction: discord.Interaction, unit: str) -> None:
        """Assign the caller the lowest available position for a selected apparatus."""
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "This command must be used in a server.",
                ephemeral=True,
            )
            return
        if not await self._require_personnel(interaction, interaction.user):
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            assignment = await self.bot.callsign_service.take_next(
                guild_id=interaction.guild.id,
                discord_id=interaction.user.id,
                unit_code=unit,
            )
        except CallsignError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        embed, files = self._assignment_embed(
            title="Callsign Assigned",
            description="You have been assigned to an SFD apparatus.",
            callsign=assignment.callsign,
            unit_name=assignment.apparatus_name,
            position_label=assignment.position_label,
            member_id=assignment.discord_id,
        )
        await interaction.followup.send(embed=embed, files=files, ephemeral=True)
        logger.info(
            "Callsign assigned: guild_id=%s discord_id=%s callsign=%s actor_id=%s",
            interaction.guild.id,
            interaction.user.id,
            assignment.callsign,
            interaction.user.id,
        )

    @callsign.command(name="my", description="Display your current SFD callsign assignment.")
    @app_commands.guild_only()
    async def my_callsign(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "This command must be used in a server.",
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        assignment = await self.bot.callsign_service.get_member_assignment(
            guild_id=interaction.guild.id,
            discord_id=interaction.user.id,
        )
        if assignment is None:
            await interaction.followup.send(
                "You don't currently have a callsign. Use `/callsign take` "
                "to join an available apparatus.",
                ephemeral=True,
            )
            return
        embed, files = self._assignment_embed(
            title="Your SFD Assignment",
            description="Your current radio callsign and apparatus assignment.",
            callsign=assignment.callsign,
            unit_name=assignment.apparatus_name,
            position_label=assignment.position_label,
            member_id=assignment.discord_id,
        )
        embed.add_field(
            name="Assigned",
            value=discord.utils.format_dt(assignment.assigned_at, style="R"),
            inline=False,
        )
        await interaction.followup.send(embed=embed, files=files, ephemeral=True)

    @callsign.command(name="release", description="Release your current SFD callsign.")
    @app_commands.guild_only()
    async def release(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "This command must be used in a server.",
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            assignment = await self.bot.callsign_service.release(
                guild_id=interaction.guild.id,
                discord_id=interaction.user.id,
                actor_id=interaction.user.id,
            )
        except CallsignNotAssigned as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        embed, files = create_sfd_embed(
            title="Callsign Released",
            description=(
                f"Your assignment **{assignment.callsign}** on **{assignment.apparatus_name}** "
                "has been released."
            ),
            footer="SFD Command • Apparatus Management",
        )
        await interaction.followup.send(embed=embed, files=files, ephemeral=True)

    @callsign.command(
        name="roster",
        description="Display the current SFD apparatus and crew roster.",
    )
    @app_commands.guild_only()
    @app_commands.describe(show_globally="Show the roster publicly in this channel.")
    async def roster(
        self,
        interaction: discord.Interaction,
        show_globally: bool = False,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "This command must be used in a server.",
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=not show_globally, thinking=True)
        roster = await self.bot.callsign_service.get_roster(interaction.guild.id)
        embed, files = self._roster_embed(roster)
        await interaction.followup.send(
            embed=embed,
            files=files,
            ephemeral=not show_globally,
        )

    @callsign.command(
        name="unit",
        description="Display the crew and available positions for one apparatus.",
    )
    @app_commands.guild_only()
    @app_commands.describe(unit="Choose the apparatus to inspect.")
    @app_commands.choices(unit=ALL_UNIT_CHOICES)
    async def unit(self, interaction: discord.Interaction, unit: str) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "This command must be used in a server.",
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        roster = await self.bot.callsign_service.get_roster(interaction.guild.id)
        selected = next((item for item in roster if item.code == unit), None)
        if selected is None:
            await interaction.followup.send("That apparatus is not configured.", ephemeral=True)
            return
        embed, files = self._roster_embed([selected], title=f"{selected.code} • {selected.name}")
        await interaction.followup.send(embed=embed, files=files, ephemeral=True)

    @callsign.command(
        name="assign",
        description="Assign a member to an apparatus. (Management only)",
    )
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(
        member="SFD member receiving the callsign.",
        unit="Apparatus to assign them to.",
        position="Position number shown by /callsign unit. Leave empty for the next self-service slot.",
    )
    @app_commands.choices(unit=ALL_UNIT_CHOICES)
    async def assign(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        unit: str,
        position: int | None = None,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "This command must be used in a server.",
                ephemeral=True,
            )
            return
        if not await self._require_personnel(interaction, member):
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            assignment = await self.bot.callsign_service.assign(
                guild_id=interaction.guild.id,
                discord_id=member.id,
                unit_code=unit,
                actor_id=interaction.user.id,
                position_number=position,
            )
        except CallsignError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        embed, files = self._assignment_embed(
            title="Callsign Assigned by Management",
            description=f"A department manager assigned **{member.mention}** to an apparatus.",
            callsign=assignment.callsign,
            unit_name=assignment.apparatus_name,
            position_label=assignment.position_label,
            member_id=assignment.discord_id,
        )
        await interaction.followup.send(embed=embed, files=files, ephemeral=True)

    @callsign.command(
        name="transfer",
        description="Transfer a member to another apparatus. (Management only)",
    )
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(
        member="Member whose callsign should be transferred.",
        unit="New apparatus assignment.",
        position="Position number shown by /callsign unit. Leave empty for the next self-service slot.",
    )
    @app_commands.choices(unit=ALL_UNIT_CHOICES)
    async def transfer(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        unit: str,
        position: int | None = None,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "This command must be used in a server.",
                ephemeral=True,
            )
            return
        if not await self._require_personnel(interaction, member):
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            assignment = await self.bot.callsign_service.transfer(
                guild_id=interaction.guild.id,
                discord_id=member.id,
                unit_code=unit,
                actor_id=interaction.user.id,
                position_number=position,
            )
        except CallsignError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        embed, files = self._assignment_embed(
            title="Callsign Transferred",
            description=(
                f"A department manager transferred **{member.mention}** "
                "to a new apparatus."
            ),
            callsign=assignment.callsign,
            unit_name=assignment.apparatus_name,
            position_label=assignment.position_label,
            member_id=assignment.discord_id,
        )
        await interaction.followup.send(embed=embed, files=files, ephemeral=True)

    @callsign.command(
        name="release-member",
        description="Release a member's callsign. (Management only)",
    )
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    async def release_member(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "This command must be used in a server.",
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            assignment = await self.bot.callsign_service.release(
                guild_id=interaction.guild.id,
                discord_id=member.id,
                actor_id=interaction.user.id,
            )
        except CallsignNotAssigned as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        embed, files = create_sfd_embed(
            title="Member Callsign Released",
            description=(
                f"{member.mention}'s callsign **{assignment.callsign}** on "
                f"**{assignment.apparatus_name}** has been released by management."
            ),
            footer="SFD Command • Apparatus Management",
        )
        await interaction.followup.send(embed=embed, files=files, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    """Load the callsign cog as a Discord extension."""
    await bot.add_cog(Callsigns(bot))
