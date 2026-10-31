"""Load and validate environment-based application settings."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from sfd_bot.core.exceptions import ConfigurationError

# config.py is at <project-root>/src/sfd_bot/config.py.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
_PLACEHOLDER_TOKENS = {
    "replace-with-your-discord-bot-token",
    "your_discord_bot_token_here",
    "put-token-here",
    "changeme",
}
_VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


def _parse_bool(name: str, value: str | None, *, default: bool) -> bool:
    """Parse a conventional environment-variable boolean or raise a clear error."""
    if value is None or not value.strip():
        return default

    normalised = value.strip().lower()
    if normalised in {"1", "true", "yes", "on"}:
        return True
    if normalised in {"0", "false", "no", "off"}:
        return False

    raise ConfigurationError(
        f"{name} must be one of true/false, yes/no, on/off, or 1/0; received an invalid value."
    )


def _parse_optional_id(name: str, value: str | None) -> int | None:
    """Parse an optional Discord snowflake-like ID as a positive integer."""
    if value is None or not value.strip():
        return None

    raw_value = value.strip()
    if not re.fullmatch(r"[0-9]+", raw_value):
        raise ConfigurationError(f"{name} must contain digits only.")

    parsed = int(raw_value)
    if parsed <= 0:
        raise ConfigurationError(f"{name} must be a positive integer.")
    return parsed


@dataclass(frozen=True, slots=True)
class Settings:
    """Validated settings used by the application.

    Keep secrets here only in memory. Never include this whole object in logs, since
    it contains the Discord bot token.
    """

    discord_bot_token: str
    dev_guild_id: int | None
    sync_global_commands: bool
    log_level: str
    database_url: str
    verified_role_id: int | None
    verification_expiry_minutes: int
    verification_max_attempts: int
    log_directory: Path
    project_root: Path


def _parse_bounded_int(
    name: str,
    value: str | None,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    """Parse an integer environment setting and enforce a safe range."""
    if value is None or not value.strip():
        return default
    try:
        parsed = int(value.strip())
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a whole number.") from exc
    if not minimum <= parsed <= maximum:
        raise ConfigurationError(f"{name} must be between {minimum} and {maximum}.")
    return parsed


def load_config() -> Settings:
    """Load `.env` (without overriding real process env vars) and validate settings."""
    load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=False)

    token = os.getenv("DISCORD_BOT_TOKEN", "").strip()
    if not token or token.lower() in _PLACEHOLDER_TOKENS:
        raise ConfigurationError(
            "DISCORD_BOT_TOKEN is missing or still contains a placeholder. "
            "Set it in the project-root .env file or in your hosting environment."
        )

    dev_guild_id = _parse_optional_id("SFD_DEV_GUILD_ID", os.getenv("SFD_DEV_GUILD_ID"))
    sync_global_commands = _parse_bool(
        "SYNC_GLOBAL_COMMANDS", os.getenv("SYNC_GLOBAL_COMMANDS"), default=False
    )

    log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO"
    if log_level not in _VALID_LOG_LEVELS:
        allowed = ", ".join(sorted(_VALID_LOG_LEVELS))
        raise ConfigurationError(f"LOG_LEVEL must be one of: {allowed}.")

    raw_database_url = os.getenv("DATABASE_URL", "").strip()
    if not raw_database_url:
        default_database_path = (PROJECT_ROOT / "data" / "sfd_bot.db").as_posix()
        raw_database_url = f"sqlite+aiosqlite:///{default_database_path}"
    if not raw_database_url.startswith(("sqlite+aiosqlite://", "postgresql+asyncpg://")):
        raise ConfigurationError(
            "DATABASE_URL must use sqlite+aiosqlite:// for local development or "
            "postgresql+asyncpg:// for PostgreSQL deployments."
        )

    verified_role_id = _parse_optional_id(
        "SFD_VERIFIED_ROLE_ID", os.getenv("SFD_VERIFIED_ROLE_ID")
    )
    verification_expiry_minutes = _parse_bounded_int(
        "VERIFICATION_EXPIRY_MINUTES",
        os.getenv("VERIFICATION_EXPIRY_MINUTES"),
        default=10,
        minimum=2,
        maximum=30,
    )
    verification_max_attempts = _parse_bounded_int(
        "VERIFICATION_MAX_ATTEMPTS",
        os.getenv("VERIFICATION_MAX_ATTEMPTS"),
        default=5,
        minimum=1,
        maximum=10,
    )

    raw_log_directory = os.getenv("LOG_DIRECTORY", "logs").strip() or "logs"
    log_directory = Path(raw_log_directory).expanduser()
    if not log_directory.is_absolute():
        log_directory = PROJECT_ROOT / log_directory

    return Settings(
        discord_bot_token=token,
        dev_guild_id=dev_guild_id,
        sync_global_commands=sync_global_commands,
        log_level=log_level,
        database_url=raw_database_url,
        verified_role_id=verified_role_id,
        verification_expiry_minutes=verification_expiry_minutes,
        verification_max_attempts=verification_max_attempts,
        log_directory=log_directory,
        project_root=PROJECT_ROOT,
    )
