"""Run entry point. 

Run from the repository root with `python -m sfd_bot.main`."""

from __future__ import annotations

import asyncio
import logging
logger = logging.getLogger(__name__)

import discord

from sfd_bot.bot import DiscordBot
from sfd_bot.config import load_config
from sfd_bot.core.exceptions import ConfigurationError
from sfd_bot.core.logging_setup import configure_logging


async def _run_bot(bot: DiscordBot, token: str) -> None:
    """Run the client with async."""
    async with bot:
        await bot.start(token)


def main() -> None:
    """Load configuration, initialise logging and run the Discord client through `bot.py`."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )

    try:
        settings = load_config()
        configure_logging(settings.log_level, settings.log_directory)
    except ConfigurationError as exc:
        logging.getLogger("sfd_bot").critical("Configuration error: %s", exc)
        raise SystemExit(2) from exc
    except OSError as exc:
        logging.getLogger("sfd_bot").critical("Could not initialise logging: %s", exc)
        raise SystemExit(2) from exc

    # Construct bot
    bot = DiscordBot(settings)
    try:
        # Bot run
        asyncio.run(_run_bot(bot, settings.discord_bot_token))
    except KeyboardInterrupt:
        logger.info("Shutdown requested from the terminal.")
    except discord.LoginFailure:
        logger.critical(
            "Discord rejected the bot token. Check DISCORD_BOT_TOKEN and regenerate the token "
            "in the Developer Portal if it has been exposed."
        )
        raise SystemExit(2) from None
    except Exception:
        logger.exception("The SFD bot stopped because of an unexpected fatal error.")
        raise SystemExit(1) from None

"""Primary Run Entry Point."""
if __name__ == "__main__":
    main()