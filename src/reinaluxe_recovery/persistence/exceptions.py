"""Persistence-foundation exceptions."""


class PersistenceError(Exception):
    """Base error for local persistence infrastructure."""


class DatabaseConfigurationError(PersistenceError):
    """Raised when a database URL is unsupported or malformed."""


class NaiveDatetimeError(PersistenceError, ValueError):
    """Raised when persistence receives a datetime without a timezone."""


class PersistenceContractError(PersistenceError, ValueError):
    """Raised when an import cannot satisfy the persistence contract."""


class URLNormalizationError(PersistenceContractError):
    """Raised when a URL cannot identify a supported HTTP(S) page."""


class PersistenceQueryError(PersistenceError):
    """Raised when a repository read fails unexpectedly."""


class PersistenceWriteError(PersistenceError):
    """Raised when an import transaction fails unexpectedly."""


class PersistenceConflictError(PersistenceWriteError):
    """Raised when a database constraint detects a concurrent conflict."""


class DatabaseLifecycleError(PersistenceError):
    """Raised when a local database cannot be initialized or migrated safely."""
