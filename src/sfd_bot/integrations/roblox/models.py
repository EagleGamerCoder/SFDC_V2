"""Typed data returned by the public Roblox user API."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RobloxUser:
    """Public Roblox account information used by SFD verification."""

    user_id: int
    username: str
    display_name: str
    description: str = ""
    is_banned: bool = False

    @property
    def profile_url(self) -> str:
        """Return the public Roblox profile URL for this account."""
        return f"https://www.roblox.com/users/{self.user_id}/profile"
