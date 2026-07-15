"""Versioned contracts for offline community intelligence and evidence review."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal, Self

from pydantic import AwareDatetime, Field, HttpUrl, JsonValue, model_validator

from reinaluxe_recovery.domain.base import DomainModel, NonEmptyText, Sha256Digest


class CommunitySourceType(StrEnum):
    """Permitted offline source categories."""

    PUBLIC_COMMUNITY_POST = "public_community_post"
    PUBLIC_COMMENT = "public_comment"
    FORUM_THREAD = "forum_thread"
    EDITORIAL_ARTICLE = "editorial_article"
    OFFICIAL_SOURCE = "official_source"
    FIRST_PARTY_OBSERVATION = "first_party_observation"
    SUPPLIER_STATEMENT = "supplier_statement"
    MEASUREMENT_RECORD = "measurement_record"
    DURABILITY_RECORD = "durability_record"
    IMAGE_EVIDENCE = "image_evidence"
    OWNER_NOTE = "owner_note"
    OTHER = "other"


class SourceVisibility(StrEnum):
    PUBLIC_SOURCE = "public_source"
    INTERNAL_ONLY = "internal_only"
    RESTRICTED_SUPPLIER_EVIDENCE = "restricted_supplier_evidence"
    PUBLISHABLE_SUMMARY_ONLY = "publishable_summary_only"


class CommunityClaimType(StrEnum):
    PRODUCT_CHANGE = "product_change"
    MATERIAL_CLAIM = "material_claim"
    CRAFTSMANSHIP_CLAIM = "craftsmanship_claim"
    HARDWARE_CLAIM = "hardware_claim"
    FACTORY_OR_BATCH_CLAIM = "factory_or_batch_claim"
    QUALITY_TIER_CLAIM = "quality_tier_claim"
    DURABILITY_CLAIM = "durability_claim"
    AUTHENTICATION_INDICATOR = "authentication_indicator"
    PRICING_OR_AVAILABILITY_OBSERVATION = "pricing_or_availability_observation"
    TREND_OR_POPULARITY_CLAIM = "trend_or_popularity_claim"
    BUYER_EXPERIENCE = "buyer_experience"
    SELLER_TERMINOLOGY = "seller_terminology"
    CORRECTION_OR_CONTRADICTION = "correction_or_contradiction"
    CONTENT_QUESTION = "content_question"
    OTHER = "other"


class ClaimExtractionMethod(StrEnum):
    MANUAL = "manual"
    OWNER_SUPPLIED = "owner_supplied"
    AI_ASSISTED_UNVERIFIED = "ai_assisted_unverified"
    DETERMINISTIC_RULE = "deterministic_rule"
    IMPORTED_EXISTING_RECORD = "imported_existing_record"


class CommunityEvidenceType(StrEnum):
    OFFICIAL_PRIMARY_SOURCE = "official_primary_source"
    FIRST_PARTY_SPECIMEN_INSPECTION = "first_party_specimen_inspection"
    FIRST_PARTY_MEASUREMENT = "first_party_measurement"
    FIRST_PARTY_LONG_TERM_USE = "first_party_long_term_use"
    SUPPLIER_CONFIRMATION = "supplier_confirmation"
    INDEPENDENT_COMMUNITY_CORROBORATION = "independent_community_corroboration"
    SINGLE_COMMUNITY_REPORT = "single_community_report"
    PHOTOGRAPHIC_EVIDENCE = "photographic_evidence"
    DOCUMENTARY_RECORD = "documentary_record"
    EDITORIAL_INFERENCE = "editorial_inference"
    UNKNOWN = "unknown"


class EvidenceConfidentiality(StrEnum):
    PUBLIC = "public"
    INTERNAL_ONLY = "internal_only"
    RESTRICTED_SUPPLIER_EVIDENCE = "restricted_supplier_evidence"


class ClaimDecision(StrEnum):
    APPROVED = "approved"
    APPROVED_WITH_QUALIFICATION = "approved_with_qualification"
    REJECTED = "rejected"
    CONTRADICTED = "contradicted"
    NEEDS_MORE_EVIDENCE = "needs_more_evidence"
    STALE = "stale"
    DUPLICATE = "duplicate"
    OUT_OF_SCOPE = "out_of_scope"


class ClaimSupportLevel(StrEnum):
    VERIFIED_PRIMARY = "verified_primary"
    VERIFIED_FIRST_PARTY = "verified_first_party"
    SUPPLIER_VERIFIED_SCOPED = "supplier_verified_scoped"
    CORROBORATED_MULTI_SOURCE = "corroborated_multi_source"
    SINGLE_SOURCE_ANECDOTE = "single_source_anecdote"
    EDITORIAL_INFERENCE = "editorial_inference"
    UNSUPPORTED = "unsupported"
    CONTRADICTED = "contradicted"


class KnowledgePublicationStatus(StrEnum):
    PUBLISHABLE = "publishable"
    PUBLISHABLE_WITH_ATTRIBUTION = "publishable_with_attribution"
    INTERNAL_ONLY = "internal_only"
    DO_NOT_PUBLISH = "do_not_publish"
    PENDING = "pending"


class CommunitySourceRecord(DomainModel):
    """Minimal retained excerpt and audit provenance for one offline source."""

    source_record_id: NonEmptyText
    schema_version: Literal["1.0"] = "1.0"
    platform: NonEmptyText
    community_or_channel: NonEmptyText
    source_type: CommunitySourceType
    source_url: HttpUrl | None = None
    source_title: str | None = Field(default=None, max_length=500)
    published_at: AwareDatetime | None = None
    retrieved_at: AwareDatetime
    language: NonEmptyText
    author_alias: str | None = Field(default=None, max_length=200)
    author_identifier_hash: Sha256Digest | None = None
    raw_excerpt: NonEmptyText
    source_summary: str | None = Field(default=None, max_length=2_000)
    source_scope: NonEmptyText
    copyright_retention_mode: NonEmptyText
    visibility: SourceVisibility
    import_batch_id: NonEmptyText
    content_hash: Sha256Digest
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_source_policy(self) -> Self:
        if self.published_at is not None and self.retrieved_at < self.published_at:
            raise ValueError("retrieved_at must not precede published_at")
        if (
            self.source_type is CommunitySourceType.SUPPLIER_STATEMENT
            and self.visibility is not SourceVisibility.RESTRICTED_SUPPLIER_EVIDENCE
        ):
            raise ValueError("supplier statements require restricted visibility")
        return self


class AtomicCandidateClaim(DomainModel):
    """One independently reviewable proposition; never an automatic fact."""

    claim_id: NonEmptyText
    schema_version: Literal["1.0"] = "1.0"
    claim_text: NonEmptyText
    normalized_claim_text: NonEmptyText
    claim_type: CommunityClaimType
    brand: str | None = Field(default=None, max_length=200)
    product_category: str | None = Field(default=None, max_length=200)
    model: str | None = Field(default=None, max_length=200)
    variant: str | None = Field(default=None, max_length=200)
    material: str | None = Field(default=None, max_length=200)
    hardware: str | None = Field(default=None, max_length=200)
    factory_or_batch_label: str | None = Field(default=None, max_length=200)
    market_or_region: str | None = Field(default=None, max_length=200)
    valid_from: AwareDatetime | None = None
    valid_until: AwareDatetime | None = None
    source_record_ids: list[NonEmptyText] = Field(min_length=1)
    evidence_record_ids: list[NonEmptyText] = Field(default_factory=list)
    extraction_method: ClaimExtractionMethod
    extraction_notes: str | None = Field(default=None, max_length=2_000)
    sensitivity: NonEmptyText
    proposed_publication_scope: NonEmptyText
    content_hash: Sha256Digest

    @model_validator(mode="after")
    def validate_claim(self) -> Self:
        if self.valid_from and self.valid_until and self.valid_until < self.valid_from:
            raise ValueError("valid_until must not precede valid_from")
        if len(self.source_record_ids) != len(set(self.source_record_ids)):
            raise ValueError("source_record_ids must be unique")
        if len(self.evidence_record_ids) != len(set(self.evidence_record_ids)):
            raise ValueError("evidence_record_ids must be unique")
        return self


class EvidenceRecord(DomainModel):
    """Scoped support for candidate claims with explicit confidentiality."""

    evidence_id: NonEmptyText
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
    reviewer_notes: str | None = Field(default=None, max_length=2_000)
    confidentiality: EvidenceConfidentiality
    content_hash: Sha256Digest

    @model_validator(mode="after")
    def validate_evidence(self) -> Self:
        if self.valid_from and self.valid_until and self.valid_until < self.valid_from:
            raise ValueError("valid_until must not precede valid_from")
        if (
            self.evidence_type is CommunityEvidenceType.SUPPLIER_CONFIRMATION
            and self.confidentiality
            is not EvidenceConfidentiality.RESTRICTED_SUPPLIER_EVIDENCE
        ):
            raise ValueError(
                "supplier confirmation requires restricted confidentiality"
            )
        return self


class ClaimReviewDecision(DomainModel):
    """Explicit human disposition of one existing candidate claim."""

    claim_id: NonEmptyText
    decision: ClaimDecision
    reviewer: NonEmptyText
    reviewed_at: AwareDatetime
    rationale: NonEmptyText
    support_level: ClaimSupportLevel
    publication_status: KnowledgePublicationStatus
    approved_wording_constraint: str | None = Field(default=None, max_length=2_000)
    required_qualification: str | None = Field(default=None, max_length=2_000)
    conflicting_claim_ids: list[NonEmptyText] = Field(default_factory=list)
    follow_up_required: bool
    follow_up_question: str | None = Field(default=None, max_length=2_000)

    @model_validator(mode="after")
    def validate_decision(self) -> Self:
        if (
            self.decision is ClaimDecision.APPROVED_WITH_QUALIFICATION
            and not self.required_qualification
        ):
            raise ValueError("approved_with_qualification requires qualification")
        if self.follow_up_required and not self.follow_up_question:
            raise ValueError("follow_up_required requires follow_up_question")
        if not self.follow_up_required and self.follow_up_question:
            raise ValueError("follow_up_question requires follow_up_required")
        if self.decision in {
            ClaimDecision.APPROVED,
            ClaimDecision.APPROVED_WITH_QUALIFICATION,
        } and self.support_level in {
            ClaimSupportLevel.UNSUPPORTED,
            ClaimSupportLevel.CONTRADICTED,
        }:
            raise ValueError("approved decisions require non-contradicted evidence")
        if (
            self.decision is ClaimDecision.CONTRADICTED
            and self.support_level is not ClaimSupportLevel.CONTRADICTED
        ):
            raise ValueError("contradicted decisions require contradicted support")
        return self


class ApplicableTimeRange(DomainModel):
    valid_from: AwareDatetime | None = None
    valid_until: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        if self.valid_from and self.valid_until and self.valid_until < self.valid_from:
            raise ValueError("valid_until must not precede valid_from")
        return self


class ApprovedKnowledgeEntry(DomainModel):
    """Human-approved, scoped knowledge derived from a reviewed claim."""

    knowledge_entry_id: NonEmptyText
    schema_version: Literal["1.0"] = "1.0"
    source_claim_id: NonEmptyText
    approved_claim: NonEmptyText
    required_qualification: str | None = None
    scope: NonEmptyText
    brand: str | None = None
    model: str | None = None
    variant: str | None = None
    material: str | None = None
    applicable_time_range: ApplicableTimeRange
    support_level: ClaimSupportLevel
    publication_status: KnowledgePublicationStatus
    evidence_ids: list[NonEmptyText] = Field(min_length=1)
    source_record_ids: list[NonEmptyText] = Field(min_length=1)
    reviewed_by: NonEmptyText
    reviewed_at: AwareDatetime
    supersedes_entry_ids: list[NonEmptyText] = Field(default_factory=list)
    contradicted_by_entry_ids: list[NonEmptyText] = Field(default_factory=list)
    stale_after: AwareDatetime | None = None
    sensitivity: NonEmptyText
    content_hash: Sha256Digest
