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
from reinaluxe_recovery.persistence.dto import (
    DatabaseLifecycleResult,
    PersistDisposition,
    PersistImportResult,
    StoredArticleVersionSummary,
    StoredCrawlSummary,
    StoredImportWarningSummary,
    StoredPageInventorySummary,
    StoredPageSummary,
)
from reinaluxe_recovery.persistence.exceptions import (
    DatabaseConfigurationError,
    DatabaseLifecycleError,
    NaiveDatetimeError,
    PersistenceConflictError,
    PersistenceContractError,
    PersistenceError,
    PersistenceQueryError,
    PersistenceWriteError,
    URLNormalizationError,
)
from reinaluxe_recovery.persistence.hashing import (
    hash_normalized_article,
    normalized_article_payload,
)
from reinaluxe_recovery.persistence.lifecycle import (
    build_sqlite_url,
    database_is_current,
    get_database_revision,
    initialize_database,
    resolve_database_path,
    upgrade_database,
)
from reinaluxe_recovery.persistence.repositories import PersistenceRepository
from reinaluxe_recovery.persistence.services import ImportPersistenceService
from reinaluxe_recovery.persistence.url_normalization import normalize_page_url

__all__ = [
    "DEFAULT_DATABASE_PATH",
    "DEFAULT_DATABASE_URL",
    "DatabaseConfigurationError",
    "DatabaseLifecycleError",
    "DatabaseLifecycleResult",
    "ImportPersistenceService",
    "NaiveDatetimeError",
    "PersistDisposition",
    "PersistImportResult",
    "PersistenceConflictError",
    "PersistenceContractError",
    "PersistenceError",
    "PersistenceQueryError",
    "PersistenceRepository",
    "PersistenceWriteError",
    "SessionFactory",
    "StoredArticleVersionSummary",
    "StoredCrawlSummary",
    "StoredImportWarningSummary",
    "StoredPageInventorySummary",
    "StoredPageSummary",
    "URLNormalizationError",
    "create_database_engine",
    "create_session_factory",
    "database_url_from_path",
    "build_sqlite_url",
    "database_is_current",
    "get_database_revision",
    "hash_normalized_article",
    "normalize_page_url",
    "normalized_article_payload",
    "persistence_metadata",
    "initialize_database",
    "resolve_database_path",
    "transactional_session",
    "upgrade_database",
]
