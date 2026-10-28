from datetime import datetime, timezone
from pathlib import Path

import discord

from sfd_bot import __version__
from sfd_bot.core.constants import SFD_RED


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