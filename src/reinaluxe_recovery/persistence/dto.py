"""Pydantic records returned by the public persistence boundary."""

from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from reinaluxe_recovery.domain import Article
from reinaluxe_recovery.domain.base import Sha256Digest
from reinaluxe_recovery.persistence.enums import (
    StoredImportStatus,
    StoredWarningSeverity,
)


class PersistenceDTO(BaseModel):
    """Strict immutable base for values detached from SQLAlchemy sessions."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
    )


class PersistDisposition(StrEnum):
    """How one part of an import was handled."""

    CREATED = "created"
    REUSED = "reused"
    VERSION_CREATED = "version_created"
    FAILED = "failed"


class PersistImportResult(PersistenceDTO):
    """Outcome of one atomic import-persistence transaction."""

    page_id: UUID
    crawl_id: UUID
    article_version_id: UUID | None = None
    page_disposition: PersistDisposition
    crawl_disposition: PersistDisposition
    article_disposition: PersistDisposition
    article_version_number: int | None = Field(default=None, ge=1)
    canonical_url: str
    source_hash: Sha256Digest
    normalized_content_hash: Sha256Digest | None = None
    warnings_persisted: int = Field(ge=0)
    persisted_at: AwareDatetime
    failure_message: str | None = None


class StoredPageSummary(PersistenceDTO):
    """Detached summary of a canonical page identity."""

    id: UUID
    canonical_url: str
    normalized_url: str
    first_seen_at: AwareDatetime
    last_seen_at: AwareDatetime
    current_article_version_id: UUID | None = None
    created_at: AwareDatetime
    updated_at: AwareDatetime


class StoredCrawlSummary(PersistenceDTO):
    """Detached summary of one imported crawl observation."""

    id: UUID
    page_id: UUID
    fetched_at: AwareDatetime
    status_code: int | None = None
    response_headers: dict[str, str]
    source_hash: Sha256Digest
    import_status: StoredImportStatus
    fatal_diagnostics: list[dict[str, Any]]
    created_at: AwareDatetime


class StoredArticleVersionSummary(PersistenceDTO):
    """Detached validated Article version and its storage metadata."""

    id: UUID
    page_id: UUID
    crawl_id: UUID
    article: Article
    normalized_content_hash: Sha256Digest
    version_number: int = Field(ge=1)
    published_at: AwareDatetime | None = None
    modified_at: AwareDatetime | None = None
    created_at: AwareDatetime


class StoredImportWarningSummary(PersistenceDTO):
    """Detached diagnostic stored for one crawl record."""

    id: UUID
    crawl_id: UUID
    code: str
    message: str
    severity: StoredWarningSeverity
    field_path: str | None = None
    source_location: str | None = None
    created_at: AwareDatetime
