"""Exceptions raised by the public Roblox API client."""

from __future__ import annotations


class RobloxAPIError(Exception):
    """The Roblox API could not return a usable response."""


class RobloxUserNotFound(RobloxAPIError):
    """The supplied Roblox username or user ID could not be found."""


class RobloxRateLimited(RobloxAPIError):
    """Roblox asked the client to slow down its requests."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class RobloxResponseError(RobloxAPIError):
    """Roblox returned data that did not match the expected response shape."""
