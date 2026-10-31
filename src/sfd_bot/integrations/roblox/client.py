"""Asynchronous client for Roblox's public user endpoints.

Username lookup uses POST /v1/usernames/users. Reading a profile description currently
uses GET /v1/users/{userId}; Roblox lists this endpoint as not recommended, so it is
isolated here and can be replaced if Roblox changes its public profile API.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

from sfd_bot.integrations.roblox.exceptions import (
    RobloxAPIError,
    RobloxRateLimited,
    RobloxResponseError,
    RobloxUserNotFound,
)
from sfd_bot.integrations.roblox.models import RobloxUser

logger = logging.getLogger(__name__)

ROBLOX_USERS_API = "https://users.roblox.com"


class RobloxClient:
    """Owns an aiohttp session and wraps public Roblox user lookups."""

    def __init__(self, *, timeout_seconds: float = 12.0) -> None:
        self._timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self._session: aiohttp.ClientSession | None = None

    async def start(self) -> None:
        """Create the shared HTTP session once during bot startup."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=self._timeout,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "SpringfieldFireDepartment-SFDCommand/0.1",
                },
            )
            logger.info("Roblox API client session started.")

    async def close(self) -> None:
        """Close the HTTP session during bot shutdown."""
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None
        logger.info("Roblox API client session closed.")

    async def _request_json(
        self,
        method: str,
        url: str,
        *,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self._session is None or self._session.closed:
            await self.start()

        assert self._session is not None

        try:
            async with self._session.request(method, url, json=json_body) as response:
                if response.status == 404:
                    raise RobloxUserNotFound("The Roblox account could not be found.")

                if response.status == 429:
                    raw_retry_after = response.headers.get("Retry-After")
                    try:
                        retry_after = float(raw_retry_after) if raw_retry_after else None
                    except ValueError:
                        retry_after = None
                    raise RobloxRateLimited(
                        "Roblox is rate-limiting profile requests. Try again shortly.",
                        retry_after=retry_after,
                    )

                if response.status >= 500:
                    raise RobloxAPIError(
                        f"Roblox is temporarily unavailable (HTTP {response.status})."
                    )

                if response.status >= 400:
                    # Do not expose arbitrary upstream response bodies to Discord users.
                    raise RobloxAPIError(
                        f"Roblox rejected the request (HTTP {response.status})."
                    )

                try:
                    payload = await response.json(content_type=None)
                except (ValueError, aiohttp.ContentTypeError) as exc:
                    raise RobloxResponseError(
                        "Roblox returned an invalid JSON response."
                    ) from exc

        except RobloxAPIError:
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            logger.warning("Roblox API request failed: %s", type(exc).__name__)
            raise RobloxAPIError(
                "Roblox could not be reached. Please try again in a moment."
            ) from exc

        if not isinstance(payload, dict):
            raise RobloxResponseError("Roblox returned an unexpected response format.")
        return payload

    async def resolve_username(self, username: str) -> RobloxUser:
        """Resolve a Roblox username to its stable numeric user ID."""
        payload = await self._request_json(
            "POST",
            f"{ROBLOX_USERS_API}/v1/usernames/users",
            json_body={
                "usernames": [username],
                "excludeBannedUsers": False,
            },
        )

        entries = payload.get("data")
        if not isinstance(entries, list) or not entries:
            raise RobloxUserNotFound(
                "That Roblox username was not found. Check the spelling and try again."
            )

        entry = entries[0]
        if not isinstance(entry, dict):
            raise RobloxResponseError("Roblox returned an invalid user record.")

        try:
            user_id = int(entry["id"])
            resolved_username = str(entry["name"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RobloxResponseError("Roblox returned incomplete user information.") from exc

        return RobloxUser(
            user_id=user_id,
            username=resolved_username,
            display_name=str(entry.get("displayName") or resolved_username),
        )

    async def get_profile(self, user_id: int) -> RobloxUser:
        """Retrieve a public profile, including its description, by stable user ID."""
        if user_id <= 0:
            raise ValueError("Roblox user ID must be positive.")

        payload = await self._request_json(
            "GET",
            f"{ROBLOX_USERS_API}/v1/users/{user_id}",
        )

        try:
            returned_id = int(payload["id"])
            username = str(payload["name"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RobloxResponseError("Roblox returned incomplete profile information.") from exc

        if returned_id != user_id:
            raise RobloxResponseError("Roblox returned a different account than requested.")

        return RobloxUser(
            user_id=returned_id,
            username=username,
            display_name=str(payload.get("displayName") or username),
            description=str(payload.get("description") or ""),
            is_banned=bool(payload.get("isBanned", False)),
        )
