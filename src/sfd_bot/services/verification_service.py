"""Application service for Roblox profile-description verification."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError

from sfd_bot.database.connection import Database
from sfd_bot.database.unit_of_work import UnitOfWork
from sfd_bot.integrations.roblox.client import RobloxClient
from sfd_bot.integrations.roblox.models import RobloxUser
from sfd_bot.services.verification_challenge_service import (
    description_contains_challenge,
    generate_challenge,
    hash_challenge,
)

logger = logging.getLogger(__name__)
_USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{3,20}$")


class VerificationError(Exception):
    """Base exception for expected verification failures."""


class InvalidRobloxUsername(VerificationError):
    """The supplied username does not have Roblox's expected format."""


class DiscordAlreadyLinked(VerificationError):
    """The Discord account already has a Roblox account linked."""


class RobloxAlreadyLinked(VerificationError):
    """The Roblox account is already linked to another Discord account."""


class ChallengeNotFound(VerificationError):
    """The challenge does not exist or does not belong to this Discord user."""


class ChallengeExpired(VerificationError):
    """The challenge has expired."""


class ChallengeUnavailable(VerificationError):
    """The challenge is no longer pending."""


class ChallengeMismatch(VerificationError):
    """The expected code has not appeared in the Roblox profile description."""

    def __init__(self, attempts_remaining: int) -> None:
        super().__init__("The verification code was not found in the profile description.")
        self.attempts_remaining = attempts_remaining


class TooManyAttempts(VerificationError):
    """The challenge was cancelled after too many unsuccessful checks."""


class VerificationRoleNotConfigured(VerificationError):
    """No verified Discord role has been configured."""


class VerificationRoleUnavailable(VerificationError):
    """The configured verified role is missing or cannot be assigned."""


@dataclass(frozen=True, slots=True)
class VerificationChallenge:
    session_id: str
    discord_id: int
    roblox_user_id: int
    roblox_username: str
    challenge: str
    expires_at: datetime
    profile_url: str


@dataclass(frozen=True, slots=True)
class VerificationOutcome:
    discord_id: int
    roblox_user_id: int
    roblox_username: str
    profile_url: str
    verified_at: datetime


@dataclass(frozen=True, slots=True)
class LinkedAccount:
    discord_id: int
    roblox_user_id: int
    roblox_username: str
    verified_at: datetime


def _as_utc(value: datetime) -> datetime:
    """Normalise SQLite-naive and PostgreSQL-aware datetimes to UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class VerificationService:
    """Coordinate account lookup, challenge storage and successful account linking."""

    def __init__(
        self,
        database: Database,
        roblox_client: RobloxClient,
        *,
        expiry_minutes: int = 10,
        max_attempts: int = 5,
    ) -> None:
        if not 2 <= expiry_minutes <= 30:
            raise ValueError("Verification expiry must be between 2 and 30 minutes.")
        if not 1 <= max_attempts <= 10:
            raise ValueError("Verification attempts must be between 1 and 10.")

        self._database = database
        self._roblox = roblox_client
        self._expiry = timedelta(minutes=expiry_minutes)
        self._max_attempts = max_attempts

    async def start(self, *, discord_id: int, username: str) -> VerificationChallenge:
        """Create a new pending challenge for a Discord member and Roblox account."""
        clean_username = username.strip()
        if not _USERNAME_PATTERN.fullmatch(clean_username):
            raise InvalidRobloxUsername(
                "Enter a valid Roblox username (3–20 letters, numbers or underscores)."
            )

        async with UnitOfWork(self._database) as uow:
            existing_link = await uow.users.get_by_discord_id(discord_id)
            if existing_link is not None:
                raise DiscordAlreadyLinked(
                    f"Your Discord account is already linked to @{existing_link.roblox_username}."
                )

        # Perform the external request outside a database transaction.
        roblox_user = await self._roblox.resolve_username(clean_username)

        async with UnitOfWork(self._database) as uow:
            existing_link = await uow.users.get_by_roblox_user_id(roblox_user.user_id)
            if existing_link is not None:
                raise RobloxAlreadyLinked(
                    "That Roblox account is already linked to a Discord account."
                )

            challenge = generate_challenge()
            expires_at = datetime.now(timezone.utc) + self._expiry
            session = await uow.verification_sessions.create_pending(
                discord_id=discord_id,
                roblox_user_id=roblox_user.user_id,
                roblox_username=roblox_user.username,
                challenge_hash=hash_challenge(challenge),
                expires_at=expires_at,
            )
            await uow.commit()

        logger.info(
            "Created Roblox verification challenge for discord_id=%s roblox_user_id=%s.",
            discord_id,
            roblox_user.user_id,
        )
        return VerificationChallenge(
            session_id=session.id,
            discord_id=discord_id,
            roblox_user_id=roblox_user.user_id,
            roblox_username=roblox_user.username,
            challenge=challenge,
            expires_at=expires_at,
            profile_url=roblox_user.profile_url,
        )

    async def check(
        self,
        *,
        discord_id: int,
        session_id: str,
    ) -> VerificationOutcome:
        """Check a Roblox profile and atomically complete the account link."""
        now = datetime.now(timezone.utc)

        # Read a detached snapshot, then perform the network request without holding a DB
        # transaction open. The pending status is checked again before committing success.
        async with UnitOfWork(self._database) as uow:
            session = await uow.verification_sessions.get_by_id(session_id)
            if session is None or session.discord_id != discord_id:
                raise ChallengeNotFound("This verification session was not found.")
            if session.status != "pending":
                if session.status == "expired":
                    raise ChallengeExpired("This verification challenge has expired.")
                raise ChallengeUnavailable("This verification challenge is no longer active.")
            if _as_utc(session.expires_at) <= now:
                await uow.verification_sessions.expire_pending(now=now)
                await uow.commit()
                raise ChallengeExpired("This verification challenge has expired.")
            if session.attempt_count >= self._max_attempts:
                await uow.verification_sessions.cancel_session(session_id)
                await uow.commit()
                raise TooManyAttempts("Too many checks were made. Start verification again.")

            roblox_user_id = session.roblox_user_id
            expected_hash = session.challenge_hash
            expires_at = _as_utc(session.expires_at)

        # This endpoint returns the public profile description. The API client isolates
        # the endpoint so a replacement can be made if Roblox changes it.
        profile: RobloxUser = await self._roblox.get_profile(roblox_user_id)
        checked_at = datetime.now(timezone.utc)

        if checked_at >= expires_at:
            async with UnitOfWork(self._database) as uow:
                await uow.verification_sessions.expire_pending(now=checked_at)
                await uow.commit()
            raise ChallengeExpired(
                "This verification challenge expired while checking the profile."
            )

        if not description_contains_challenge(profile.description, expected_hash):
            async with UnitOfWork(self._database) as uow:
                attempts = await uow.verification_sessions.increment_attempt(
                    session_id,
                    checked_at=checked_at,
                )
                if attempts is None:
                    latest = await uow.verification_sessions.get_by_id(session_id)
                    if latest is not None and _as_utc(latest.expires_at) <= checked_at:
                        await uow.verification_sessions.expire_pending(now=checked_at)
                        await uow.commit()
                        raise ChallengeExpired("This verification challenge has expired.")
                    raise ChallengeUnavailable("This verification challenge is no longer active.")

                if attempts >= self._max_attempts:
                    await uow.verification_sessions.cancel_session(session_id)
                    await uow.commit()
                    raise TooManyAttempts(
                        "The maximum number of checks was reached. Start verification again."
                    )

                await uow.commit()

            raise ChallengeMismatch(self._max_attempts - attempts)

        try:
            async with UnitOfWork(self._database) as uow:
                # Re-check ownership/status/expiry after the Roblox request to prevent a
                # stale or superseded challenge from being used.
                current = await uow.verification_sessions.get_by_id(session_id)
                if current is None or current.discord_id != discord_id:
                    raise ChallengeNotFound("This verification session was not found.")
                if current.status != "pending":
                    raise ChallengeUnavailable("This verification challenge is no longer active.")
                completed_at = datetime.now(timezone.utc)
                if _as_utc(current.expires_at) <= completed_at:
                    await uow.verification_sessions.expire_pending(now=completed_at)
                    await uow.commit()
                    raise ChallengeExpired("This verification challenge expired during the check.")

                discord_link = await uow.users.get_by_discord_id(discord_id)
                if discord_link is not None:
                    raise DiscordAlreadyLinked("Your Discord account is already linked.")

                roblox_link = await uow.users.get_by_roblox_user_id(profile.user_id)
                if roblox_link is not None:
                    raise RobloxAlreadyLinked(
                        "That Roblox account is already linked to a Discord account."
                    )

                marked = await uow.verification_sessions.mark_completed(
                    session_id,
                    completed_at=completed_at,
                )
                if not marked:
                    raise ChallengeUnavailable("This verification challenge is no longer active.")

                await uow.users.create_link(
                    discord_id=discord_id,
                    roblox_user_id=profile.user_id,
                    roblox_username=profile.username,
                    verified_at=completed_at,
                )
                await uow.commit()

        except IntegrityError as exc:
            logger.info(
                "Concurrent duplicate verification prevented for discord_id=%s roblox_user_id=%s.",
                discord_id,
                profile.user_id,
            )
            raise RobloxAlreadyLinked(
                "This Discord or Roblox account was linked by another verification attempt."
            ) from exc

        logger.info(
            "Roblox verification completed for discord_id=%s roblox_user_id=%s.",
            discord_id,
            profile.user_id,
        )
        return VerificationOutcome(
            discord_id=discord_id,
            roblox_user_id=profile.user_id,
            roblox_username=profile.username,
            profile_url=profile.profile_url,
            verified_at=completed_at,
        )

    async def cancel(self, *, discord_id: int, session_id: str) -> bool:
        """Cancel a pending challenge owned by the specified Discord account."""
        async with UnitOfWork(self._database) as uow:
            session = await uow.verification_sessions.get_by_id(session_id)
            if session is None or session.discord_id != discord_id:
                return False
            changed = await uow.verification_sessions.cancel_session(session_id)
            if changed:
                await uow.commit()
            return changed

    async def get_link(self, discord_id: int) -> LinkedAccount | None:
        """Retrieve the verified account link for a Discord user."""
        async with UnitOfWork(self._database) as uow:
            link = await uow.users.get_by_discord_id(discord_id)
            if link is None:
                return None
            return LinkedAccount(
                discord_id=link.discord_id,
                roblox_user_id=link.roblox_user_id,
                roblox_username=link.roblox_username,
                verified_at=_as_utc(link.verified_at),
            )
