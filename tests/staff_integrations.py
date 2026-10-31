"""Discord commands and aspects for staff management.

- Promotions 🟢
- Infractions 🟢
- LOAs
- Shifts
- Sessions 🟢


// README.md

All commands are set by the permission check of '@app_commands.checks.has_permissions(manage_roles=True)'
Change to fit the roles that should have access.

Change the global variables below to fit as well.

Shifts and LOA will require Database connections
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

import asyncio
from datetime import datetime, timezone
from dataclasses import dataclass, field

# // GLOBALS 
LOG_CHANNEL_ID_PROMOTE=1564736411339329586 # Maybe set by per-server config
LOG_CHANNEL_ID_INFRACT=1564736411339329586 # Maybe set by per-server config
SESSION_CHANNEL_ID=1234567890 # Maybe set by per-server config
EMBED_COLOUR=0xc5a45d
PUNISHMENT_ROLE_IDS={
    "s1":1234567890, # Maybe created by bot
    "s2":1234567890, # Maybe created by bot
    "t":1234567890, # Maybe created by bot
}

def create_embed(title: str, desc: str) -> discord.Embed:
    embed = discord.Embed(
        title=title,
        description=desc,
        colour=discord.Colour(EMBED_COLOUR),
    )
    embed.set_footer(
        text=f"Loomi CAD • ER:LC • {datetime.now(timezone.utc)}"
    )
    return embed

def check_infractions(member: discord.Member) -> discord.Role | None:
    roles = get_infraction_roles(member.guild)
    missing_roles = [name for name, role in roles.items() if role is None]

    if missing_roles:
        raise RuntimeError(
            f"Missing configured infraction roles: {missing_roles}"
        )
    
    member_roles = {role.id for role in member.roles}
    if PUNISHMENT_ROLE_IDS["t"] in member_roles:
        return None
    if PUNISHMENT_ROLE_IDS["s2"] in member_roles:
        return member.guild.get_role(PUNISHMENT_ROLE_IDS["t"])
    if PUNISHMENT_ROLE_IDS["s1"] in member_roles:
        return member.guild.get_role(PUNISHMENT_ROLE_IDS["s2"])
    return member.guild.get_role(PUNISHMENT_ROLE_IDS["s1"])

def get_infraction_roles(guild: discord.Guild) -> dict[str, discord.Role]:
    roles = {}
    for level, role_id in PUNISHMENT_ROLE_IDS.items():
        role = guild.get_role(role_id)
        if role is None:
            raise RuntimeError(
                f"Could not find configured infraction role: {level}"
            )
        roles[level] = role
    return roles

@dataclass
class ActiveSession:
    # // Session info
    
    guild_id: int
    required_votes: int
    host_id: int
    voters: set[int] = field(default_factory=set)

    status: str = "voting"

    signup_message: discord.Message | None = None
    started_message: discord.Message | None = None

    view: "SessionVoteView | None" = None

class SessionVoteView(discord.ui.View):
    def __init__(self, cog: Staff_Integrations):
        super().__init__(timeout=None)
        self.cog = cog

    # // Voting Buttons

    @discord.ui.button(label="Vote", emoji="✅", style=discord.ButtonStyle.success, custom_id="loomi_session_vote")
    async def vote(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.cog.handle_session_vote(interaction, add_vote=True)

    @discord.ui.button(label="Remove Vote", emoji="✖️", style=discord.ButtonStyle.secondary, custom_id="loomi_session_remove_vote")
    async def remove_vote(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.cog.handle_session_vote(interaction, add_vote=False)

class Staff_Integrations(commands.Cog):
    infraction = app_commands.Group(
        name="infraction",
        description="Manage personnel infractions."
    )
    session = app_commands.Group(
        name="session",
        description="Gameplay sessions."
    )
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.active_session: ActiveSession | None = None
        self.ended_message: discord.Message | None = None
        self.session_lock = asyncio.Lock()

    """PROMOTE"""

    @app_commands.command(name="promote", description="Promote a user.")
    @app_commands.describe(member="The user that will be promoted.", oldrole="The old role the user is promoting from.", newrole="The new role to promote to.", reason="Reason of Promotion.")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def promote(self, interaction: discord.Interaction, member: discord.Member, oldrole:discord.Role, newrole: discord.Role, reason: str) -> None:
        if (newrole not in member.roles) and (oldrole in member.roles):
            await member.add_roles(newrole, reason=reason)
            await member.remove_roles(oldrole, reason=reason)
        elif (newrole not in member.roles) and (oldrole not in member.roles):
            await interaction.response.send_message(f"User does not have the old role: {oldrole.name}.", ephemeral=True) 
            return
        elif (newrole in member.roles) and (oldrole in member.roles):
            await interaction.response.send_message(f"User does has the new role: {newrole.name}, already.", ephemeral=True)
            return
        else:
            await interaction.response.send_message(f"An error occured.", ephemeral=True)
            return

        # // Log
        embed = create_embed("Promotion Log", f"{member.mention} has been promoted because of `{reason}`.")
        embed.add_field(
            name="Roles",
            value=(
                f"Old Role: {oldrole.mention}",
                f"New Role: {oldrole.mention}"
            ),
            inline=False
        )

        if interaction.guild is None:
            return
        channel_id = int(LOG_CHANNEL_ID_PROMOTE)
        log_channel = interaction.client.get_channel(channel_id)
        if log_channel is None:
            log_channel = await interaction.client.fetch_channel(channel_id)

        if isinstance(log_channel, discord.TextChannel):
            await log_channel.send(embed=embed)

    """INFRACTION"""

    @app_commands.command(name="infract", description="Infracts a user.")
    @app_commands.describe(member="The user that will be infracted.", reason="Reason of infraction.")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def infract(self, interaction: discord.Interaction, member: discord.Member, reason: str) -> None:
        punishment = check_infractions(member=member)
        if punishment is None:
            await interaction.response.send_message(f"{member.mention} has already reached termination.", ephemeral=True)
            return

        # // Log
        embed = create_embed("Infraction Log", f"{member.mention} has been infracted because of `{reason}`.")
        embed.add_field(
            name="Actions Taken",
            value=(
                f"Given Punishment: {punishment.mention}",
                f"Submitted by: {interaction.user.mention}"
            ),
            inline=False
        )

        if interaction.guild is None:
            return
        channel_id = int(LOG_CHANNEL_ID_INFRACT)
        log_channel = interaction.client.get_channel(channel_id)
        if log_channel is None:
            log_channel = await interaction.client.fetch_channel(channel_id)

        if isinstance(log_channel, discord.TextChannel):
            await log_channel.send(embed=embed)

    @infraction.command(name="view", description="Views a user's infraction status.")
    @app_commands.describe(member="The user that will be viewed.")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def infraction_view(self, interaction: discord.Interaction, member: discord.Member) -> None:
        roles = get_infraction_roles(member.guild)
        member_role_ids = {role.id for role in member.roles}
        active_roles = [role for role in roles.values() if role.id in member_role_ids]
        embed = create_embed("Infraction Status", f"Infraction status for {member.mention}.")
        embed.set_thumbnail(url=member.display_avatar.url)
        if any(role.id == roles["t"].id for role in active_roles):
            status = roles["t"].mention
            status_text = "Terminated"
        elif any(role.id == roles["s2"].id for role in active_roles):
            status = roles["s2"].mention
            status_text = "Second Strike"
        elif any(role.id == roles["S1"].id for role in active_roles):
            status = roles["s1"].mention
            status_text = "First Strike"
        else:
            status = "None"
            status_text = "No active infractions"
        embed.add_field(
            name="Current Status",
            value=f"**{status_text}**\n{status}",
            inline=False
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @infraction.command(name="reset", description="Resets a user's infractions.")
    @app_commands.describe(member="The user that will be reseted.")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def infraction_reset(self, interaction: discord.Interaction, member: discord.Member) -> None:
        roles = get_infraction_roles(member.guild)
        member_role_ids = {role.id for role in member.roles}
        roles_to_remove = [role for role in roles.values() if role.id in member_role_ids]

        if not roles_to_remove:
            await interaction.response.send_message(f"{member.mention} has no active infractions.", ephemeral=True)
            return
        try:
            await member.remove_roles(*roles_to_remove, reason=f"Infraction reset by {interaction.user}")

        except discord.Forbidden:
            await interaction.response.send_message("I cannot remove these roles. Check my Manage Roles permission and role hierarchy.", ephemeral=True)
            return
        except discord.HTTPException:
            await interaction.response.send_message("An error occurred while resetting the member's infractions.", ephemeral=True,)
            return

        embed = create_embed("Infraction Reset", f"All active infraction roles have been removed from {member.mention}.")
        embed.add_field(
            name="Removed Roles",
            value="\n".join(
                role.mention for role in roles_to_remove
            ),
            inline=False,
        )
        embed.add_field(
            name="Reset By",
            value=interaction.user.mention,
            inline=True,
        )
        await interaction.response.send_message(embed=embed, ephemeral=False)

    """SESSION"""

    def build_session_embed(self, session: ActiveSession) -> discord.Embed:
        embed = create_embed("Loomi | Session",
            (
                "A session is being organised!\n\n"
                "Press **Vote** below if you can attend. "
                "You can remove your vote at any time before the session begins."
            ),
        )
        embed.add_field(
            name="Session Status",
            value=(
                "🟡 Awaiting Participants"
                if session.status == "voting"
                else "🟢 Session Started"
            ),
            inline=True,
        )
        embed.add_field(
            name="Required Votes",
            value=f"`{session.required_votes}`",
            inline=True,
        )
        embed.add_field(
            name="Current Votes",
            value=f"`{len(session.voters)}/{session.required_votes}`",
            inline=True,
        )

        # // Voter display
        if session.voters:
            voter_list = [f"<@{user_id}>" for user_id in sorted(session.voters)]
            displayed_voters = voter_list[:20] # embed text limit
            voter_text = "\n".join(displayed_voters)
            if len(voter_list) > 20:
                voter_text += f"\n...and {len(voter_list) - 20} more."
        else:
            voter_text = "No votes have been submitted yet."

        embed.add_field(
            name=f"Participants ({len(session.voters)})",
            value=voter_text,
            inline=False,
        )
        embed.add_field(
            name="Session Hosted By",
            value=f"<@{session.host_id}>",
            inline=False,
        )

        return embed

    async def handle_session_vote(self, interaction: discord.Interaction, *, add_vote: bool) -> None:
        async with self.session_lock:
            session = self.active_session
            if (session is None or session.status != "voting" or session.signup_message is None or interaction.message is None or interaction.message.id != session.signup_message.id):
                await interaction.response.send_message("There is no active session accepting votes.", ephemeral=True)
                return

            user_id = interaction.user.id
            if add_vote:
                if user_id in session.voters:
                    await interaction.response.send_message("You have already voted for this session.", ephemeral=True)
                    return
                session.voters.add(user_id)
            else:
                if user_id not in session.voters:
                    await interaction.response.send_message("You have not voted for this session.", ephemeral=True)
                    return
                session.voters.remove(user_id)

            # // Check threshhold
            if len(session.voters) >= session.required_votes:
                session.status = "started"

                # // Disable buttons
                if session.view is not None:
                    for item in session.view.children:
                        if isinstance(item, discord.ui.Button):
                            item.disabled = True

                await interaction.response.edit_message(embed=self.build_session_embed(session), view=session.view)

                await self.start_session_announcement(session)
                return

            # // Update embed
            await interaction.response.edit_message(embed=self.build_session_embed(session), view=session.view)

    async def start_session_announcement(self, session: ActiveSession) -> None:
        if session.signup_message is None:
            return

        guild = self.bot.get_guild(session.guild_id)
        if guild is None:
            return

        channel = guild.get_channel(SESSION_CHANNEL_ID)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(SESSION_CHANNEL_ID)
            except discord.HTTPException:
                return
        if not isinstance(channel, discord.TextChannel):
            return

        voter_mentions = " ".join(f"<@{user_id}>" for user_id in sorted(session.voters))

        # // Session started embed
        embed = create_embed(
            "Session Started",
            (
                "The required number of participants has been reached!\n\n"
                "**The session has officially started.**\n"
                "All participants should now join the game."
            ),
        )
        embed.add_field(
            name="Participants",
            value=f"`{len(session.voters)}`",
            inline=True,
        )
        embed.add_field(
            name="Hosted By",
            value=f"<@{session.host_id}>",
            inline=True,
        )

        try:
            session.started_message = await channel.send(
                content=(
                    f"@here {voter_mentions}\n"
                    "**The session has started! Please join the game now or you will face moderation.**"
                ),
                embed=embed,
                allowed_mentions=discord.AllowedMentions(
                    everyone=True,
                    users=True,
                    roles=False,
                ),
            )
        except discord.Forbidden:
            print("Loomi Session: Missing permissions to send the start announcement.")
        except discord.HTTPException as exc:
            print(f"Loomi Session: Failed to send start announcement: {exc}")

    @session.command(name="start", description="Start an Loomi session signup.")
    @app_commands.describe(required_votes="Number of votes required to start the session.")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_roles=True)
    async def session_start(self, interaction: discord.Interaction, required_votes: app_commands.Range[int, 1, 50]) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("This command can only be used inside a server.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        async with self.session_lock:
            if self.active_session is not None:
                await interaction.followup.send("There is already an active Loomi session.", ephemeral=True)
                return

            # // Get configured session channel
            try:
                channel = self.bot.get_channel(SESSION_CHANNEL_ID)

                if channel is None:
                    channel = await self.bot.fetch_channel(SESSION_CHANNEL_ID)
                if not isinstance(channel, discord.TextChannel):
                    raise RuntimeError("SESSION_CHANNEL_ID does not point to a text channel.")
                if channel.guild.id != interaction.guild.id:
                    raise RuntimeError("The configured session channel belongs to another server.")
            except (discord.HTTPException, RuntimeError) as exc:
                await interaction.followup.send(f"Could not access the session channel: {exc}", ephemeral=True)
                return

            # // Remove olf embed
            if self.ended_message is not None:
                try:
                    await self.ended_message.delete()
                except discord.NotFound:
                    pass
                except discord.HTTPException:
                    await interaction.followup.send("I couldn't remove the previous session-ended message. - Check my Manage Messages permission.", ephemeral=True)
                    return

                self.ended_message = None

            # // Create session state
            session = ActiveSession(guild_id=interaction.guild.id, required_votes=required_votes, host_id=interaction.user.id)
            view = SessionVoteView(self)
            session.view = view
            embed = self.build_session_embed(session)

            try:
                session.signup_message = await channel.send(embed=embed, view=view)
            except discord.HTTPException as exc:
                await interaction.followup.send(f"Failed to create the session signup: {exc}", ephemeral=True)
                return

            # // Save
            self.active_session = session
            await interaction.followup.send(
                f"Successfully published the Loomi session signup in {channel.mention}.\n"
                f"Required votes: **{required_votes}**",
                ephemeral=True,
            )

    @session.command(name="end", description="End the current Loomi session.")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_roles=True)
    async def session_end(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("This command can only be used inside a server.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)

        async with self.session_lock:
            session = self.active_session
            if session is None or session.guild_id != interaction.guild.id:
                await interaction.followup.send("There is currently no active Loomi session.", ephemeral=True)
                return

            # // Get configured session channel
            try:
                channel = self.bot.get_channel(SESSION_CHANNEL_ID)

                if channel is None:
                    channel = await self.bot.fetch_channel(SESSION_CHANNEL_ID)
                if not isinstance(channel, discord.TextChannel):
                    raise RuntimeError("SESSION_CHANNEL_ID does not point to a text channel.")
                if channel.guild.id != interaction.guild.id:
                    raise RuntimeError("The configured session channel belongs to another server.")
            except (discord.HTTPException, RuntimeError) as exc:
                await interaction.followup.send(f"Could not access the session channel: {exc}", ephemeral=True)
                return

            deletion_failed = False

            # // Delete signup message
            messages_to_delete = [session.signup_message, session.started_message]
            for message in messages_to_delete:
                if message is None:
                    continue
                try:
                    await message.delete()
                except discord.NotFound:
                    pass
                except discord.HTTPException:
                    deletion_failed = True

            # // Create ended embed
            embed = create_embed(
                "Session Ended",
                (
                    "The session has officially ended."
                    "\n\nThank you to everyone who participated."
                ),
            )
            embed.add_field(
                name="Hosted By",
                value=f"<@{session.host_id}>",
                inline=True,
            )
            embed.add_field(
                name="Participants",
                value=f"`{len(session.voters)}`",
                inline=True,
            )
            
            try:
                self.ended_message = await channel.send(embed=embed)
            except discord.HTTPException:
                await interaction.followup.send("The session messages were processed, but I couldn't send the session-ended embed.", ephemeral=True)
                return

            # // Clearup
            self.active_session = None
            if deletion_failed:
                await interaction.followup.send("The session has ended, but I couldn't delete all previous session messages. Check my Manage Messages permission.", ephemeral=True)
            else:
                await interaction.followup.send("The Loomi session has successfully ended.", ephemeral=True)