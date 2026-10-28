"""Application-specific exceptions."""


class SFDApplicationError(Exception):
    """Base class for expected application errors."""


class ConfigurationError(SFDApplicationError):
    """Raised when required application configuration is absent or invalid."""


class JSONConfigurationError(SFDApplicationError):
    """Raised when a JSON configuration file cannot be loaded or validated."""


class PermissionDenied(SFDApplicationError):
    """Raised when a service rejects an unauthorised action."""


class ResourceNotFound(SFDApplicationError):
    """Raised when a requested application record does not exist."""


class ExternalServiceError(SFDApplicationError):
    """Raised when an external API cannot provide a usable response."""
