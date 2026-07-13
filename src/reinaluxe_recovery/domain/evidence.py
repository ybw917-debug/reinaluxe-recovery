"""Factual evidence, community claims, and human review contracts."""

from typing import Self
from uuid import UUID, uuid4

from pydantic import AwareDatetime, Field, HttpUrl, model_validator

from reinaluxe_recovery.domain.base import DomainModel, NonEmptyText
from reinaluxe_recovery.domain.enums import (
    ClaimVerificationStatus,
    EvidenceConfidence,
    EvidenceSourceType,
    RecoveryAction,
    ReviewDecision,
)


class EvidenceReference(DomainModel):
    """Traceable factual evidence used by a derived finding or assessment."""

    id: UUID = Field(default_factory=uuid4)
    source_type: EvidenceSourceType
    source_name: NonEmptyText
    supports: NonEmptyText
    observed_at: AwareDatetime
    collected_at: AwareDatetime
    confidence: EvidenceConfidence
    source_url: HttpUrl | None = None
    source_record_id: str | None = Field(default=None, min_length=1, max_length=500)
    excerpt: str | None = Field(default=None, max_length=2_000)
    is_primary_source: bool = False
    notes: str | None = Field(default=None, max_length=2_000)
    related_article_ids: list[UUID] = Field(default_factory=list)
    related_snapshot_ids: list[UUID] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_provenance(self) -> Self:
        """Require a locator and chronologically valid collection time."""
        if self.source_url is None and self.source_record_id is None:
            raise ValueError("source_url or source_record_id is required")
        if self.collected_at < self.observed_at:
            raise ValueError("collected_at must not precede observed_at")
        return self


class CommunityClaim(DomainModel):
    """Community statement kept separate from verified factual evidence."""

    id: UUID = Field(default_factory=uuid4)
    statement: NonEmptyText
    source_platform: NonEmptyText
    collected_at: AwareDatetime
    verification_status: ClaimVerificationStatus = ClaimVerificationStatus.UNVERIFIED
    source_url: HttpUrl | None = None
    source_record_id: str | None = Field(default=None, min_length=1, max_length=500)
    author_alias: str | None = Field(default=None, max_length=200)
    posted_at: AwareDatetime | None = None
    context: str | None = Field(default=None, max_length=2_000)
    corroborating_evidence_ids: list[UUID] = Field(default_factory=list)
    related_article_ids: list[UUID] = Field(default_factory=list)
    related_topic_ids: list[UUID] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_claim_provenance(self) -> Self:
        """Require provenance and evidence for a non-unverified status."""
        if self.source_url is None and self.source_record_id is None:
            raise ValueError("source_url or source_record_id is required")
        if self.posted_at is not None and self.collected_at < self.posted_at:
            raise ValueError("collected_at must not precede posted_at")
        if (
            self.verification_status is not ClaimVerificationStatus.UNVERIFIED
            and not self.corroborating_evidence_ids
        ):
            raise ValueError("corroborated or contradicted claims require evidence")
        return self


class HumanReviewDecision(DomainModel):
    """Explicit owner or reviewer judgment about a generated recommendation."""

    id: UUID = Field(default_factory=uuid4)
    article_id: UUID
    reviewer_id: NonEmptyText
    decision: ReviewDecision
    decided_at: AwareDatetime
    rationale: NonEmptyText
    recommendation_id: UUID | None = None
    approved_action: RecoveryAction | None = None
    evidence_reference_ids: list[UUID] = Field(default_factory=list)
    community_claim_ids: list[UUID] = Field(default_factory=list)
    supersedes_decision_id: UUID | None = None

    @model_validator(mode="after")
    def validate_approved_action(self) -> Self:
        """Keep approved editorial action explicit and unambiguous."""
        if self.decision is ReviewDecision.APPROVED and self.approved_action is None:
            raise ValueError("approved decisions require approved_action")
        if (
            self.decision is not ReviewDecision.APPROVED
            and self.approved_action is not None
        ):
            raise ValueError("approved_action is only valid for approved decisions")
        return self
