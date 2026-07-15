"""Versioned contracts for approved-knowledge content opportunity planning."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal, Self

from pydantic import AwareDatetime, Field, HttpUrl, JsonValue, model_validator

from reinaluxe_recovery.domain.base import DomainModel, NonEmptyText, Sha256Digest
from reinaluxe_recovery.domain.community import (
    ApplicableTimeRange,
    ClaimSupportLevel,
    KnowledgePublicationStatus,
)


class ContentOpportunityType(StrEnum):
    UPDATE_EXISTING_SECTION = "update_existing_section"
    ADD_SUPPORTING_SECTION = "add_supporting_section"
    ADD_FAQ = "add_faq"
    CORRECT_EXISTING_CLAIM = "correct_existing_claim"
    QUALIFY_EXISTING_CLAIM = "qualify_existing_claim"
    REPLACE_UNSUPPORTED_CLAIM = "replace_unsupported_claim"
    EVIDENCE_ENRICHMENT = "evidence_enrichment"
    FRESHNESS_UPDATE = "freshness_update"
    NEW_ARTICLE_CANDIDATE = "new_article_candidate"
    INTERNAL_ONLY_RESEARCH = "internal_only_research"
    NO_ACTION = "no_action"


class OpportunityDecisionValue(StrEnum):
    APPROVED = "approved"
    APPROVED_WITH_CHANGES = "approved_with_changes"
    REJECTED = "rejected"
    DEFER = "defer"
    NEEDS_MORE_EVIDENCE = "needs_more_evidence"
    DUPLICATE = "duplicate"
    CONFLICTS_WITH_PAGE_ROLE = "conflicts_with_page_role"
    USE_FOR_NEW_ARTICLE = "use_for_new_article"
    INTERNAL_ONLY = "internal_only"
    NO_ACTION = "no_action"


class OpportunityConfidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class OpportunityOwnerStatus(StrEnum):
    PENDING = "pending"


class DraftingPriority(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NOT_SCHEDULED = "not_scheduled"


class KnowledgeSnapshotManifest(DomainModel):
    snapshot_id: NonEmptyText
    schema_version: Literal["1.0"] = "1.0"
    created_at: AwareDatetime
    source_batch_ids: list[NonEmptyText] = Field(min_length=1)
    knowledge_entry_ids: list[NonEmptyText]
    entry_count: int = Field(ge=0)
    approved_count: int = Field(ge=0)
    qualified_count: int = Field(ge=0)
    internal_only_count: int = Field(ge=0)
    excluded_entry_ids: list[NonEmptyText]
    source_hashes: dict[NonEmptyText, Sha256Digest]
    snapshot_hash: Sha256Digest

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        if self.entry_count != len(self.knowledge_entry_ids):
            raise ValueError("entry_count must equal knowledge_entry_ids length")
        if self.source_batch_ids != sorted(set(self.source_batch_ids)):
            raise ValueError("source_batch_ids must be sorted and unique")
        if self.knowledge_entry_ids != sorted(set(self.knowledge_entry_ids)):
            raise ValueError("knowledge_entry_ids must be sorted and unique")
        if self.excluded_entry_ids != sorted(set(self.excluded_entry_ids)):
            raise ValueError("excluded_entry_ids must be sorted and unique")
        return self


class PageContextRecord(DomainModel):
    page_context_id: NonEmptyText
    schema_version: Literal["1.0"] = "1.0"
    page_url: HttpUrl
    page_identity_id: NonEmptyText
    article_version_id: NonEmptyText
    page_content_hash: Sha256Digest
    current_title: NonEmptyText
    current_h1: NonEmptyText
    current_meta_description: str | None
    current_role: NonEmptyText
    final_role: NonEmptyText
    primary_intent: NonEmptyText
    secondary_intents: list[NonEmptyText]
    brand: str | None
    models: list[NonEmptyText]
    materials: list[NonEmptyText]
    content_cluster: NonEmptyText
    hub_url: HttpUrl | None = None
    supporting_urls: list[HttpUrl]
    closest_overlap_urls: list[HttpUrl]
    approved_operations: list[NonEmptyText]
    deferred_operations: list[NonEmptyText]
    prohibited_operations: list[NonEmptyText]
    section_outline: list[NonEmptyText]
    factual_blockers: list[NonEmptyText]
    visual_blockers: list[NonEmptyText]
    freshness_status: NonEmptyText
    context_created_at: AwareDatetime
    context_hash: Sha256Digest

    @model_validator(mode="after")
    def validate_context(self) -> Self:
        for field_name in (
            "secondary_intents",
            "models",
            "materials",
            "supporting_urls",
            "closest_overlap_urls",
            "approved_operations",
            "deferred_operations",
            "prohibited_operations",
            "factual_blockers",
            "visual_blockers",
        ):
            values = getattr(self, field_name)
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} must be unique")
        if "merge" in self.final_role.casefold():
            raise ValueError("final_role must not be a merge candidate")
        return self


class ContentOpportunity(DomainModel):
    opportunity_id: NonEmptyText
    schema_version: Literal["1.0"] = "1.0"
    knowledge_entry_ids: list[NonEmptyText] = Field(min_length=1)
    page_context_ids: list[NonEmptyText]
    opportunity_type: ContentOpportunityType
    target_page_url: HttpUrl | None = None
    proposed_new_article_topic: str | None = None
    proposed_location: NonEmptyText
    user_question: NonEmptyText
    mapping_reason: NonEmptyText
    entity_match_evidence: list[NonEmptyText]
    intent_compatibility: list[NonEmptyText]
    support_level: ClaimSupportLevel
    publication_status: KnowledgePublicationStatus
    required_qualification: str | None
    temporal_scope: ApplicableTimeRange
    conflict_flags: list[NonEmptyText]
    overlap_risk: list[NonEmptyText]
    paired_page_dependencies: list[HttpUrl]
    evidence_ids: list[NonEmptyText] = Field(min_length=1)
    source_claim_ids: list[NonEmptyText] = Field(min_length=1)
    confidence: OpportunityConfidence
    owner_decision_status: OpportunityOwnerStatus = OpportunityOwnerStatus.PENDING
    content_hash: Sha256Digest

    @model_validator(mode="after")
    def validate_target(self) -> Self:
        if self.opportunity_type is ContentOpportunityType.NEW_ARTICLE_CANDIDATE:
            if self.target_page_url is not None or not self.proposed_new_article_topic:
                raise ValueError("new article candidates require a topic and no target")
        elif self.opportunity_type in {
            ContentOpportunityType.INTERNAL_ONLY_RESEARCH,
            ContentOpportunityType.NO_ACTION,
        }:
            if self.target_page_url is not None:
                raise ValueError(
                    "internal/no-action opportunities cannot target a page"
                )
        elif self.target_page_url is None:
            raise ValueError("existing-page opportunities require target_page_url")
        if (
            self.publication_status is KnowledgePublicationStatus.INTERNAL_ONLY
            and self.opportunity_type
            not in {
                ContentOpportunityType.INTERNAL_ONLY_RESEARCH,
                ContentOpportunityType.NO_ACTION,
            }
        ):
            raise ValueError("internal-only knowledge cannot create publishable work")
        return self


class OpportunityReviewDecision(DomainModel):
    opportunity_id: NonEmptyText
    decision: OpportunityDecisionValue
    reviewer: NonEmptyText
    reviewed_at: AwareDatetime
    rationale: NonEmptyText
    target_page_url: HttpUrl | None = None
    approved_opportunity_type: ContentOpportunityType | None = None
    approved_location: str | None = None
    required_qualification: str | None = None
    paired_page_requirement: list[HttpUrl]
    drafting_priority: DraftingPriority
    follow_up_required: bool
    follow_up_question: str | None = None

    @model_validator(mode="after")
    def validate_review(self) -> Self:
        if self.follow_up_required != bool(self.follow_up_question):
            raise ValueError("follow-up flag and question must be supplied together")
        if self.decision is OpportunityDecisionValue.APPROVED_WITH_CHANGES and not (
            self.target_page_url
            or self.approved_opportunity_type
            or self.approved_location
            or self.required_qualification
        ):
            raise ValueError("approved_with_changes requires an explicit change")
        return self


class ContentChangeManifest(DomainModel):
    change_manifest_id: NonEmptyText
    schema_version: Literal["1.0"] = "1.0"
    created_at: AwareDatetime
    page_context_snapshot_id: NonEmptyText
    page_context_snapshot_hash: Sha256Digest
    knowledge_snapshot_id: NonEmptyText
    knowledge_snapshot_hash: Sha256Digest
    approved_opportunity_ids: list[NonEmptyText]
    affected_page_urls: list[HttpUrl]
    page_version_constraints: dict[str, dict[str, NonEmptyText]]
    allowed_knowledge_entry_ids: list[NonEmptyText]
    prohibited_claim_ids: list[NonEmptyText]
    required_qualifications: dict[str, NonEmptyText]
    approved_change_types: dict[str, ContentOpportunityType]
    prohibited_operations: list[NonEmptyText]
    paired_page_requirements: dict[str, list[HttpUrl]]
    drafting_constraints: list[NonEmptyText]
    validation_requirements: list[NonEmptyText]
    owner_approval: dict[str, JsonValue]
    manifest_hash: Sha256Digest
