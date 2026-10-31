"""Generate and validate one-time Roblox profile-description challenges."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets

CHALLENGE_PREFIX = "SFD-VERIFY-"
CHALLENGE_TOKEN_BYTES = 18
_CHALLENGE_PATTERN = re.compile(
    rf"(?<![A-Za-z0-9_-]){re.escape(CHALLENGE_PREFIX)}([A-Za-z0-9_-]{{24}})(?![A-Za-z0-9_-])"
)


def generate_challenge() -> str:
    """Create a hard-to-guess challenge code suitable for a profile description."""
    return f"{CHALLENGE_PREFIX}{secrets.token_urlsafe(CHALLENGE_TOKEN_BYTES)}"


def hash_challenge(challenge: str) -> str:
    """Return the SHA-256 digest stored in the database, never the raw challenge."""
    return hashlib.sha256(challenge.encode("utf-8")).hexdigest()


def description_contains_challenge(description: str, expected_hash: str) -> bool:
    """Find a correctly formatted challenge in a public profile description."""
    for match in _CHALLENGE_PATTERN.finditer(description[:2000]):
        candidate = f"{CHALLENGE_PREFIX}{match.group(1)}"
        candidate_hash = hash_challenge(candidate)
        if hmac.compare_digest(candidate_hash, expected_hash):
            return True
    return False
