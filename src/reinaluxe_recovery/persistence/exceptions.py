"""Persistence-foundation exceptions."""


class PersistenceError(Exception):
    """Base error for local persistence infrastructure."""


class DatabaseConfigurationError(PersistenceError):
    """Raised when a database URL is unsupported or malformed."""


class NaiveDatetimeError(PersistenceError, ValueError):
    """Raised when persistence receives a datetime without a timezone."""
