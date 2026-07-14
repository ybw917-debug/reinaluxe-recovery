"""Local SQLite persistence foundation."""

from reinaluxe_recovery.persistence.database import (
    DEFAULT_DATABASE_PATH,
    DEFAULT_DATABASE_URL,
    SessionFactory,
    create_database_engine,
    create_session_factory,
    database_url_from_path,
    persistence_metadata,
    transactional_session,
)
from reinaluxe_recovery.persistence.exceptions import (
    DatabaseConfigurationError,
    NaiveDatetimeError,
    PersistenceError,
)

__all__ = [
    "DEFAULT_DATABASE_PATH",
    "DEFAULT_DATABASE_URL",
    "DatabaseConfigurationError",
    "NaiveDatetimeError",
    "PersistenceError",
    "SessionFactory",
    "create_database_engine",
    "create_session_factory",
    "database_url_from_path",
    "persistence_metadata",
    "transactional_session",
]
