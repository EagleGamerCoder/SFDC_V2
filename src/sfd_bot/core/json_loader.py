"""Small, reusable JSON configuration loader with clear error messages."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sfd_bot.core.exceptions import JSONConfigurationError


def load_json_object(path: Path) -> dict[str, Any]:
    """Load a JSON file and require its top-level value to be an object."""
    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except FileNotFoundError as exc:
        raise JSONConfigurationError(f"JSON configuration file was not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise JSONConfigurationError(
            f"Invalid JSON in {path} at line {exc.lineno}, column {exc.colno}."
        ) from exc
    except OSError as exc:
        raise JSONConfigurationError(f"Could not read JSON configuration file: {path}") from exc

    if not isinstance(data, dict):
        raise JSONConfigurationError(f"The top-level JSON value in {path} must be an object.")
    return data
