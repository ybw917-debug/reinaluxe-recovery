"""Strict input contracts for an offline community import manifest."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, Field, JsonValue

from reinaluxe_recovery.domain.base import DomainModel, NonEmptyText, Sha256Digest
from reinaluxe_recovery.domain.community import (
    ClaimExtractionMethod,
    CommunityClaimType,
    CommunityEvidenceType,
    CommunitySourceType,
    EvidenceConfidentiality,
    KnowledgePublicationStatus,
    SourceVisibility,
)


class LocalRecordReference(DomainModel):
    """Confined local file plus an explicit text encoding."""

    input_file: Path
    encoding: NonEmptyText
    input_format: Literal["text", "json"]


class SourceDraft(DomainModel):
    source_record_id: str | None = None
    schema_version: Literal["1.0"] = "1.0"
    platform: NonEmptyText
    community_or_channel: NonEmptyText
    source_type: CommunitySourceType
    source_url: str | None = None
    source_title: str | None = None
    published_at: AwareDatetime | None = None
    retrieved_at: AwareDatetime
    language: NonEmptyText
    author_alias: str | None = None
    author_identifier_hash: Sha256Digest | None = None
    raw_excerpt: NonEmptyText
    source_summary: str | None = None
    source_scope: NonEmptyText
    copyright_retention_mode: NonEmptyText
    visibility: SourceVisibility | None = None
    import_batch_id: str | None = None
    content_hash: Sha256Digest | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class ClaimDraft(DomainModel):
    claim_id: str | None = None
    schema_version: Literal["1.0"] = "1.0"
    claim_text: NonEmptyText
    normalized_claim_text: str | None = None
    claim_type: CommunityClaimType
    brand: str | None = None
    product_category: str | None = None
    model: str | None = None
    variant: str | None = None
    material: str | None = None
    hardware: str | None = None
    factory_or_batch_label: str | None = None
    market_or_region: str | None = None
    valid_from: AwareDatetime | None = None
    valid_until: AwareDatetime | None = None
    source_record_ids: list[NonEmptyText] = Field(min_length=1)
    evidence_record_ids: list[NonEmptyText] = Field(default_factory=list)
    extraction_method: ClaimExtractionMethod
    extraction_notes: str | None = None
    sensitivity: NonEmptyText
    proposed_publication_scope: NonEmptyText
    content_hash: Sha256Digest | None = None


class EvidenceDraft(DomainModel):
    evidence_id: str | None = None
    schema_version: Literal["1.0"] = "1.0"
    evidence_type: CommunityEvidenceType
    source_record_ids: list[NonEmptyText] = Field(min_length=1)
    evidence_summary: NonEmptyText
    applicable_claim_ids: list[NonEmptyText] = Field(min_length=1)
    scope_constraints: NonEmptyText
    provenance: NonEmptyText | dict[str, JsonValue]
    collected_at: AwareDatetime
    valid_from: AwareDatetime | None = None
    valid_until: AwareDatetime | None = None
    reviewer_notes: str | None = None
    confidentiality: EvidenceConfidentiality | None = None
    content_hash: Sha256Digest | None = None


class CommunityImportManifest(DomainModel):
    schema_version: Literal["1.0"] = "1.0"
    import_batch_id: NonEmptyText
    created_at: AwareDatetime
    default_encoding: NonEmptyText = "utf-8"
    sources: list[dict[str, JsonValue]] = Field(min_length=1)
    candidate_claims: list[dict[str, JsonValue]] = Field(default_factory=list)
    evidence_records: list[dict[str, JsonValue]] = Field(default_factory=list)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


REVIEW_DECISION_FIELDS = {
    "owner_decision",
    "owner_rationale",
    "support_level",
    "publication_status",
    "reviewer",
    "reviewed_at",
    "approved_wording_constraint",
    "required_qualification",
    "conflicting_claim_ids",
    "follow_up_required",
    "follow_up_question",
}

PENDING_PUBLICATION_STATUS = KnowledgePublicationStatus.PENDING.value
