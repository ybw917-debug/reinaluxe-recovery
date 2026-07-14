"""Strict versioned contracts for deterministic offline batch imports."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path, PurePath
from typing import Literal, Self

from pydantic import AwareDatetime, Field, HttpUrl, JsonValue, model_validator

from reinaluxe_recovery.domain.base import DomainModel, NonEmptyText, Sha256Digest
from reinaluxe_recovery.importing import ImportWarning
from reinaluxe_recovery.persistence import PersistDisposition


class BatchEntryStatus(StrEnum):
    """Final handling state for one manifest entry."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    NOT_ATTEMPTED = "not_attempted"


class BatchOverallStatus(StrEnum):
    """Aggregate outcome derived from entry results."""

    SUCCEEDED = "succeeded"
    COMPLETED_WITH_FAILURES = "completed_with_failures"


class BatchFailureKind(StrEnum):
    """Stable category used by the CLI exit-code policy."""

    FILE = "file"
    IMPORT = "import"
    PERSISTENCE = "persistence"


class BatchManifestEntry(DomainModel):
    """One owner-provided HTML observation in a local manifest."""

    entry_id: NonEmptyText
    html_path: Path
    source_url: HttpUrl
    fetched_at: AwareDatetime | None = None
    status_code: int = Field(default=200, ge=100, le=599)
    headers: dict[str, str] | None = None
    enabled: bool = True
    notes: str | None = Field(default=None, max_length=2_000)
    expected_source_hash: Sha256Digest | None = None


class BatchManifest(DomainModel):
    """Versioned ordered set of fully local HTML observations."""

    contract_version: Literal["1.0"]
    batch_id: NonEmptyText
    created_at: AwareDatetime
    default_fetched_at: AwareDatetime | None = None
    default_headers: dict[str, str] | None = None
    entries: list[BatchManifestEntry] = Field(min_length=1)
    metadata: dict[str, JsonValue] | None = None

    @model_validator(mode="after")
    def validate_entries(self) -> Self:
        """Reject ambiguous identities, paths, and observation timestamps."""
        entry_ids: set[str] = set()
        paths: set[str] = set()
        for entry in self.entries:
            if entry.entry_id in entry_ids:
                raise ValueError(f"duplicate entry_id: {entry.entry_id}")
            entry_ids.add(entry.entry_id)
            path_key = PurePath(entry.html_path).as_posix().casefold()
            if path_key in paths:
                raise ValueError(f"duplicate html_path: {entry.html_path}")
            paths.add(path_key)
            if entry.fetched_at is None and self.default_fetched_at is None:
                raise ValueError(
                    f"entry {entry.entry_id!r} requires fetched_at or "
                    "default_fetched_at"
                )
        return self

    def effective_fetched_at(self, entry: BatchManifestEntry) -> AwareDatetime:
        """Return the validated entry timestamp with manifest inheritance."""
        value = entry.fetched_at or self.default_fetched_at
        assert value is not None
        return value

    def effective_headers(self, entry: BatchManifestEntry) -> dict[str, str]:
        """Merge manifest headers with entry overrides without mutating either."""
        headers = dict(self.default_headers or {})
        headers.update(entry.headers or {})
        return headers


class BatchImportOptions(DomainModel):
    """Explicit selection and error-handling controls for one batch run."""

    continue_on_error: bool = True
    persist_failed: bool = True
    dry_run: bool = False
    limit: int | None = Field(default=None, ge=1)
    entry_ids: list[NonEmptyText] | None = None

    @model_validator(mode="after")
    def reject_duplicate_filters(self) -> Self:
        if self.entry_ids is not None and len(self.entry_ids) != len(
            set(self.entry_ids)
        ):
            raise ValueError("duplicate entry_ids are not allowed")
        return self


class BatchEntryResult(DomainModel):
    """Detached result for one entry, including skipped and failed entries."""

    entry_id: str
    html_path: Path
    source_url: HttpUrl
    status: BatchEntryStatus
    import_success: bool
    persistence_success: bool
    page_disposition: PersistDisposition | None = None
    crawl_disposition: PersistDisposition | None = None
    article_disposition: PersistDisposition | None = None
    article_version_number: int | None = Field(default=None, ge=1)
    warnings: list[ImportWarning] = Field(default_factory=list)
    fatal_diagnostics: list[str] = Field(default_factory=list)
    error_message: str | None = None
    failure_kind: BatchFailureKind | None = None
    started_at: AwareDatetime
    completed_at: AwareDatetime
    duration_ms: int = Field(ge=0)
    source_hash: Sha256Digest | None = None


class BatchImportResult(DomainModel):
    """Stable aggregate batch report derived from ordered entry results."""

    contract_version: Literal["1.0"] = "1.0"
    batch_id: str
    manifest_path: Path
    database_path: Path | None = None
    started_at: AwareDatetime
    completed_at: AwareDatetime
    total_entries: int = Field(ge=1)
    enabled_entries: int = Field(ge=0)
    attempted_entries: int = Field(ge=0)
    succeeded_entries: int = Field(ge=0)
    failed_entries: int = Field(ge=0)
    skipped_entries: int = Field(ge=0)
    created_pages: int = Field(ge=0)
    reused_pages: int = Field(ge=0)
    created_crawls: int = Field(ge=0)
    reused_crawls: int = Field(ge=0)
    created_article_versions: int = Field(ge=0)
    reused_article_versions: int = Field(ge=0)
    results: list[BatchEntryResult]
    overall_status: BatchOverallStatus
