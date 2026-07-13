"""Raw crawl and scoped performance snapshot contracts."""

from datetime import date
from typing import Literal, Self
from uuid import UUID, uuid4

from pydantic import AwareDatetime, Field, HttpUrl, model_validator

from reinaluxe_recovery.domain.base import DomainModel, NonEmptyText, Sha256Digest
from reinaluxe_recovery.domain.enums import EvidenceSourceType, MetricScope


class CrawlSnapshot(DomainModel):
    """Raw, immutable observation from a future crawl implementation."""

    contract_version: Literal["1.0"] = "1.0"
    id: UUID = Field(default_factory=uuid4)
    requested_url: HttpUrl
    captured_at: AwareDatetime
    source_system: NonEmptyText
    final_url: HttpUrl | None = None
    http_status: int | None = Field(default=None, ge=100, le=599)
    response_headers: dict[str, str] = Field(default_factory=dict)
    redirect_chain: list[HttpUrl] = Field(default_factory=list)
    raw_html: str | None = None
    response_content_type: str | None = Field(default=None, max_length=200)
    content_hash: Sha256Digest | None = None
    observed_canonical_url: HttpUrl | None = None
    robots_allowed: bool | None = None
    fetch_duration_ms: int | None = Field(default=None, ge=0)
    error_message: str | None = Field(default=None, max_length=2_000)

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        """Require either an HTTP observation or a documented fetch error."""
        if self.http_status is None and self.error_message is None:
            raise ValueError("http_status or error_message is required")
        return self


class PerformanceSnapshot(DomainModel):
    """Time-bounded page-level or site-level performance observation."""

    contract_version: Literal["1.0"] = "1.0"
    id: UUID = Field(default_factory=uuid4)
    scope: MetricScope
    source_type: EvidenceSourceType
    captured_at: AwareDatetime
    period_start: date
    period_end: date
    article_id: UUID | None = None
    page_url: HttpUrl | None = None
    clicks: int | None = Field(default=None, ge=0)
    impressions: int | None = Field(default=None, ge=0)
    click_through_rate: float | None = Field(default=None, ge=0, le=1)
    average_position: float | None = Field(default=None, ge=0)
    indexed: bool | None = None
    custom_metrics: dict[str, float] = Field(default_factory=dict)
    dimensions: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_scope_and_period(self) -> Self:
        """Prevent mixing page and site metrics in one snapshot."""
        if self.period_end < self.period_start:
            raise ValueError("period_end must not precede period_start")
        if self.scope is MetricScope.PAGE:
            if self.page_url is None and self.article_id is None:
                raise ValueError("page scope requires page_url or article_id")
        elif self.page_url is not None or self.article_id is not None:
            raise ValueError("site scope must not include page_url or article_id")

        core_metrics = (
            self.clicks,
            self.impressions,
            self.click_through_rate,
            self.average_position,
            self.indexed,
        )
        if all(metric is None for metric in core_metrics) and not self.custom_metrics:
            raise ValueError("at least one performance metric is required")
        return self
