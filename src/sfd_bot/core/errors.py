"""Shared handling for Discord application-command errors."""

from __future__ import annotations

import logging

import discord
from discord import app_commands

logger = logging.getLogger(__name__)


async def handle_app_command_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
) -> None:
    """Log an application-command error and return a safe user-facing response."""
    original = error.original if isinstance(error, app_commands.CommandInvokeError) else error

    if isinstance(original, app_commands.CommandOnCooldown):
        message = f"Please wait {original.retry_after:.1f} seconds before trying that again."
        await _send_ephemeral(interaction, message)
        return

    if isinstance(original, app_commands.MissingPermissions):
        await _send_ephemeral(interaction, "You don't have the Discord permissions required for that command.")
        logger.warning(
            "Command permission check failed for user_id=%s command=%s",
            interaction.user.id,
            _command_name(interaction),
        )
        return

    if isinstance(original, app_commands.CheckFailure):
        await _send_ephemeral(interaction, "You aren't authorised to use that command here.")
        logger.warning(
            "Command check failed for user_id=%s command=%s",
            interaction.user.id,
            _command_name(interaction),
        )
        return

    logger.error(
        "Unhandled application-command error for user_id=%s command=%s",
        interaction.user.id,
        _command_name(interaction),
        exc_info=(type(original), original, original.__traceback__),
    )
    await _send_ephemeral(
        interaction,
        "Something went wrong while running that command. The issue has been logged.",
    )


def _command_name(interaction: discord.Interaction) -> str:
    """Return a safe command label for logs."""
    command = interaction.command
    return command.qualified_name if command is not None else "unknown"


async def _send_ephemeral(interaction: discord.Interaction, message: str) -> None:
    """Respond privately, using a follow-up if the interaction was already answered."""
    try:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
    except discord.HTTPException:
        logger.warning("Could not send error response for interaction_id=%s", interaction.id)
