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
    PersistDisposition,
    PersistImportResult,
    StoredArticleVersionSummary,
    StoredCrawlSummary,
    StoredImportWarningSummary,
    StoredPageSummary,
)
from reinaluxe_recovery.persistence.exceptions import (
    DatabaseConfigurationError,
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
from reinaluxe_recovery.persistence.repositories import PersistenceRepository
from reinaluxe_recovery.persistence.services import ImportPersistenceService
from reinaluxe_recovery.persistence.url_normalization import normalize_page_url

__all__ = [
    "DEFAULT_DATABASE_PATH",
    "DEFAULT_DATABASE_URL",
    "DatabaseConfigurationError",
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
    "StoredPageSummary",
    "URLNormalizationError",
    "create_database_engine",
    "create_session_factory",
    "database_url_from_path",
    "hash_normalized_article",
    "normalize_page_url",
    "normalized_article_payload",
    "persistence_metadata",
    "transactional_session",
]
