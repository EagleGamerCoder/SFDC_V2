from datetime import datetime, timezone
from pathlib import Path

import discord

from sfd_bot import __version__
from sfd_bot.core.constants import SFD_RED
from sfd_bot.core.json_loader import load_json_object

# Project root:
# SFD-Discord-Bot/
PROJECT_ROOT = Path(__file__).resolve().parents[3]

BRANDING_DIR = PROJECT_ROOT / "assets" / "branding"

BADGE_PATH = BRANDING_DIR / "SFD_Main_Badge.png"
BANNER_PATH = BRANDING_DIR / "SFD_Bot_Banner.png"


def create_sfd_embed(*, title: str, description: str | None = None, footer: str | None = None,) -> tuple[discord.Embed, list[discord.File]]:
    """Create a consistently branded SFD embed and its image attachments."""

    # Fail clearly if an expected graphic is missing.
    if not BADGE_PATH.is_file():
        raise FileNotFoundError(
            f"SFD badge image was not found: {BADGE_PATH}"
        )

    if not BANNER_PATH.is_file():
        raise FileNotFoundError(
            f"SFD banner image was not found: {BANNER_PATH}"
        )

    embed = discord.Embed(
        title=title,
        description=description,
        colour=discord.Colour(SFD_RED),
        timestamp=datetime.now(timezone.utc),
    )

    # Department identity in the author area.
    embed.set_author(
        name="SPRINGFIELD FIRE DEPARTMENT COMMAND",
        icon_url="attachment://sfd-badge.png",
    )

    # Wide image displayed beneath the embed's main content.
    embed.set_image(
        url="attachment://sfd-banner.png"
    )

    # A consistent footer on all SFD embeds.
    embed.set_footer(
        text=footer or f"SFD Command • v{__version__}"
    )

    files = [
        discord.File(
            BADGE_PATH,
            filename="sfd-badge.png",
        ),
        discord.File(
            BANNER_PATH,
            filename="sfd-banner.png",
        ),
    ]

    return embed, files

def create_verification_panel() -> tuple[discord.Embed, list[discord.File]]:
    """Build the public SFD account-verification panel from its JSON definition."""
    panel_path = PROJECT_ROOT / "data" / "panels" / "verification.json"
    panel = load_json_object(panel_path)

    title = str(panel.get("title", "Roblox Account Verification"))
    description = str(
        panel.get(
            "description",
            "Link your Roblox account to access the appropriate SFD Discord channels.",
        )
    )
    embed, files = create_sfd_embed(
        title=title,
        description=description,
        footer="SFD Command • Account Verification",
    )

    instructions = panel.get("instructions", [])
    if isinstance(instructions, list) and instructions:
        instruction_text = "\n".join(
            f"{index}. {str(instruction)}"
            for index, instruction in enumerate(instructions, start=1)
        )
        embed.add_field(name="How it works", value=instruction_text, inline=False)

    privacy_notice = panel.get("privacy_notice")
    if privacy_notice:
        embed.add_field(name="Privacy", value=str(privacy_notice), inline=False)

    return embed, files
