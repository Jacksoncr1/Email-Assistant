class EmailAssistantError(Exception):
    """Base exception for expected module errors."""


class ConfigurationError(EmailAssistantError):
    """Raised when required runtime configuration is missing or unsafe."""


class CryptoError(EmailAssistantError):
    """Raised when encrypted data cannot be protected or recovered."""


class NotFoundError(EmailAssistantError):
    """Raised when a tenant-scoped resource does not exist."""


class TenantAccessError(EmailAssistantError):
    """Raised when a resource exists but belongs to another tenant."""


class ProviderError(EmailAssistantError):
    """Raised when an email provider adapter fails."""
