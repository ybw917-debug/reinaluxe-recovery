"""Strict contracts for conservative public-site acquisition."""

from collections import Counter
from enum import StrEnum
from pathlib import Path
from typing import Literal, Self
from uuid import uuid4

from pydantic import AwareDatetime, Field, HttpUrl, JsonValue, model_validator

from reinaluxe_recovery.domain.base import DomainModel, NonEmptyText, Sha256Digest


class AcquisitionSourceType(StrEnum):
    SITEMAP = "sitemap"
    URL_LIST = "url_list"


class AcquisitionStatus(StrEnum):
    DISCOVERED = "discovered"
    FETCHED = "fetched"
    SKIPPED = "skipped"
    FAILED = "failed"
    UNCHANGED = "unchanged"


class AcquisitionOverallStatus(StrEnum):
    SUCCEEDED = "succeeded"
    COMPLETED_WITH_FAILURES = "completed_with_failures"


class AcquisitionRequest(DomainModel):
    contract_version: Literal["1.0"] = "1.0"
    acquisition_id: NonEmptyText = Field(default_factory=lambda: str(uuid4()))
    created_at: AwareDatetime
    source_type: AcquisitionSourceType
    sitemap_urls: tuple[HttpUrl, ...] | None = None
    explicit_urls: tuple[HttpUrl, ...] | None = None
    allowed_hosts: frozenset[str] = Field(min_length=1)
    output_directory: Path
    user_agent: NonEmptyText
    request_timeout_seconds: float = Field(default=20.0, gt=0)
    delay_between_requests_seconds: float = Field(default=1.0, ge=0)
    maximum_urls: int | None = Field(default=None, ge=1)
    include_patterns: tuple[str, ...] | None = None
    exclude_patterns: tuple[str, ...] | None = None
    overwrite_existing: bool = False
    metadata: dict[str, JsonValue] | None = None

    @model_validator(mode="after")
    def validate_source(self) -> Self:
        if self.source_type is AcquisitionSourceType.SITEMAP and not self.sitemap_urls:
            raise ValueError("sitemap source requires sitemap_urls")
        if (
            self.source_type is AcquisitionSourceType.URL_LIST
            and not self.explicit_urls
        ):
            raise ValueError("url_list source requires explicit_urls")
        if any(
            "@" in host or ":" in host or "/" in host for host in self.allowed_hosts
        ):
            raise ValueError("allowed_hosts must contain host names only")
        sensitive = {
            "authorization",
            "cookie",
            "password",
            "secret",
            "token",
            "api_key",
            "api-key",
        }

        def check_metadata(value: JsonValue) -> None:
            if isinstance(value, dict):
                for key, nested in value.items():
                    if key.casefold() in sensitive:
                        raise ValueError(
                            f"credential-like metadata key is not allowed: {key}"
                        )
                    check_metadata(nested)
            elif isinstance(value, list):
                for nested in value:
                    check_metadata(nested)

        if self.metadata is not None:
            check_metadata(self.metadata)
        return self


class AcquiredPage(DomainModel):
    entry_id: NonEmptyText
    requested_url: HttpUrl
    final_url: HttpUrl | None = None
    canonical_candidate: HttpUrl | None = None
    fetched_at: AwareDatetime | None = None
    status_code: int | None = Field(default=None, ge=100, le=599)
    content_type: str | None = None
    response_headers: dict[str, str] = Field(default_factory=dict)
    source_hash: Sha256Digest | None = None
    snapshot_path: Path | None = None
    status: AcquisitionStatus
    error_type: str | None = None
    error_message: str | None = None
    redirect_chain: tuple[HttpUrl, ...] = ()
    duration_ms: int = Field(ge=0)


class AcquisitionResult(DomainModel):
    contract_version: Literal["1.0"] = "1.0"
    acquisition_id: str
    started_at: AwareDatetime
    completed_at: AwareDatetime
    source_type: AcquisitionSourceType
    output_directory: Path
    discovered_count: int = 0
    attempted_count: int = 0
    fetched_count: int = 0
    unchanged_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    pages: tuple[AcquiredPage, ...]
    manifest_path: Path | None = None
    overall_status: AcquisitionOverallStatus = AcquisitionOverallStatus.SUCCEEDED

    @model_validator(mode="after")
    def derive_counts(self) -> Self:
        counts = Counter(page.status for page in self.pages)
        attempted = (
            counts[AcquisitionStatus.FETCHED]
            + counts[AcquisitionStatus.UNCHANGED]
            + counts[AcquisitionStatus.FAILED]
        )
        object.__setattr__(self, "discovered_count", len(self.pages))
        object.__setattr__(self, "attempted_count", attempted)
        object.__setattr__(self, "fetched_count", counts[AcquisitionStatus.FETCHED])
        object.__setattr__(self, "unchanged_count", counts[AcquisitionStatus.UNCHANGED])
        object.__setattr__(self, "skipped_count", counts[AcquisitionStatus.SKIPPED])
        object.__setattr__(self, "failed_count", counts[AcquisitionStatus.FAILED])
        object.__setattr__(
            self,
            "overall_status",
            AcquisitionOverallStatus.COMPLETED_WITH_FAILURES
            if counts[AcquisitionStatus.FAILED]
            else AcquisitionOverallStatus.SUCCEEDED,
        )
        return self
