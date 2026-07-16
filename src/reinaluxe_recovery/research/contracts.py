"""Versioned public contracts for article-driven multi-source research."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import (
    AwareDatetime,
    Field,
    HttpUrl,
    JsonValue,
    StringConstraints,
    model_validator,
)

from reinaluxe_recovery.community.normalization import content_hash
from reinaluxe_recovery.domain.base import DomainModel, NonEmptyText, Sha256Digest

ContractVersion = Literal["1.0"]
Identifier = Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]


class ResearchMode(StrEnum):
    ARTICLE_RESEARCH = "article_research"
    TOPIC_BUILD = "topic_build"
    TOPIC_REFRESH = "topic_refresh"
    CLAIM_VERIFY = "claim_verify"
    EVIDENCE_GAP_FILL = "evidence_gap_fill"
    VISUAL_RESEARCH = "visual_research"


class SourceLane(StrEnum):
    COMMUNITY_REDDIT = "community_reddit"
    COMMUNITY_FORUMS = "community_forums"
    PRIMARY_OFFICIAL = "primary_official"
    EXPERT_EDITORIAL = "expert_editorial"
    COMMERCIAL_OBSERVATION = "commercial_observation"
    VISUAL_IMAGE = "visual_image"


class EvidenceRelationship(StrEnum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    LIMITS = "limits"
    CONTEXTUALIZES = "contextualizes"


class EvidenceAssessment(StrEnum):
    CORROBORATED = "corroborated"
    DISPUTED = "disputed"
    INSUFFICIENT = "insufficient_evidence"
    SINGLE_SOURCE = "single_source"


class OwnerDecisionValue(StrEnum):
    APPROVED = "approved"
    APPROVED_WITH_CHANGES = "approved_with_changes"
    REJECTED = "rejected"
    DEFER = "defer"


class PermissionStatus(StrEnum):
    UNKNOWN = "unknown"
    REVIEW_REQUIRED = "review_required"
    PERMITTED = "permitted"
    NOT_PERMITTED = "not_permitted"


class ReviewStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    DEFERRED = "deferred"


class TemporalScope(DomainModel):
    schema_version: ContractVersion = "1.0"
    start_date: date | None = None
    end_date: date | None = None
    description: str | None = None

    @model_validator(mode="after")
    def validate_dates(self) -> Self:
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must not precede start_date")
        return self


class SourceLanePolicy(DomainModel):
    schema_version: ContractVersion = "1.0"
    source_lane: SourceLane
    priority: int = Field(ge=1)
    source_quota: int = Field(default=5, ge=0)
    query_quota: int = Field(default=3, ge=0)
    enabled: bool = True
    allowed_domains: list[str] = Field(default_factory=list)
    excluded_domains: list[str] = Field(default_factory=list)
    path_requirements: list[str] = Field(default_factory=list)


class _ResearchRequest(DomainModel):
    schema_version: ContractVersion = "1.0"
    research_id: Identifier
    mode: ResearchMode
    target_article_url: HttpUrl | None = None
    article_version_id: str | None = None
    article_content_hash: Sha256Digest | None = None
    topic_ids: list[Identifier] = Field(default_factory=list)
    owner_objective: NonEmptyText
    target_audience: NonEmptyText
    source_lane_priorities: list[SourceLanePolicy] = Field(min_length=1)
    language: NonEmptyText = "en"
    alternate_languages: list[NonEmptyText] = Field(default_factory=list)
    region: NonEmptyText = "global"
    temporal_scope: TemporalScope = Field(default_factory=TemporalScope)
    brand_scope: list[str] = Field(default_factory=list)
    model_scope: list[str] = Field(default_factory=list)
    excluded_subjects: list[str] = Field(default_factory=list)
    image_research_required: bool = False
    maximum_search_calls: int = Field(default=20, ge=1)
    maximum_sources: int = Field(default=50, ge=1)
    maximum_image_candidates: int = Field(default=25, ge=0)
    output_directory: Path
    provider: NonEmptyText = "zhipu"
    query_families: list[NonEmptyText] = Field(default_factory=list)
    research_questions: list[NonEmptyText] = Field(default_factory=list)
    article_source_path: Path | None = None
    production_database_path: Path | None = None
    approved_knowledge_paths: list[Path] = Field(default_factory=list)
    prior_research_paths: list[Path] = Field(default_factory=list)
    request_hash: Sha256Digest | None = None

    @model_validator(mode="after")
    def validate_request(self) -> Self:
        lanes = [policy.source_lane for policy in self.source_lane_priorities]
        if len(lanes) != len(set(lanes)):
            raise ValueError("source_lane_priorities must contain unique lanes")
        if not any(
            policy.enabled and policy.query_quota
            for policy in self.source_lane_priorities
        ):
            raise ValueError(
                "at least one source lane must have a positive query quota"
            )
        expected = self.computed_request_hash()
        if self.request_hash is not None and self.request_hash != expected:
            raise ValueError("request_hash does not match request content")
        return self

    def computed_request_hash(self) -> str:
        return content_hash(self.model_dump(mode="json", exclude={"request_hash"}))

    def with_request_hash(self) -> Self:
        return self.model_copy(update={"request_hash": self.computed_request_hash()})


class ArticleResearchRequest(_ResearchRequest):
    mode: Literal[
        ResearchMode.ARTICLE_RESEARCH,
        ResearchMode.CLAIM_VERIFY,
        ResearchMode.EVIDENCE_GAP_FILL,
        ResearchMode.VISUAL_RESEARCH,
    ]

    @model_validator(mode="after")
    def require_article_target(self) -> Self:
        if (
            not self.target_article_url
            and not self.article_version_id
            and not self.article_source_path
        ):
            raise ValueError(
                "article research requires an article URL, version ID, or source path"
            )
        return self


class TopicResearchRequest(_ResearchRequest):
    mode: Literal[
        ResearchMode.TOPIC_BUILD,
        ResearchMode.TOPIC_REFRESH,
        ResearchMode.CLAIM_VERIFY,
        ResearchMode.EVIDENCE_GAP_FILL,
        ResearchMode.VISUAL_RESEARCH,
    ]

    @model_validator(mode="after")
    def require_topic_target(self) -> Self:
        if (
            not self.topic_ids
            and not self.research_questions
            and not self.query_families
        ):
            raise ValueError(
                "topic research requires topic IDs, questions, or query families"
            )
        return self


class ResearchTopic(DomainModel):
    schema_version: ContractVersion = "1.0"
    topic_id: Identifier
    name: NonEmptyText
    definition: NonEmptyText
    aliases: list[str] = Field(default_factory=list)
    synonyms: list[str] = Field(default_factory=list)
    parent_topic_id: str | None = None
    query_templates: list[str] = Field(default_factory=list)
    refresh_after: date | None = None
    deleted_at: AwareDatetime | None = None


class ResearchQuestion(DomainModel):
    schema_version: ContractVersion = "1.0"
    question_id: Identifier
    question: NonEmptyText
    rationale: NonEmptyText
    topic_ids: list[str] = Field(default_factory=list)
    target_article_section: str | None = None
    evidence_gap: str | None = None
    priority: int = Field(default=1, ge=1)


class ResearchQuery(DomainModel):
    schema_version: ContractVersion = "1.0"
    query_id: Identifier
    research_question_id: Identifier
    source_lane: SourceLane
    search_text: NonEmptyText
    positive_terms: list[str] = Field(default_factory=list)
    exclusion_terms: list[str] = Field(default_factory=list)
    temporal_range: TemporalScope = Field(default_factory=TemporalScope)
    brand_scope: list[str] = Field(default_factory=list)
    model_scope: list[str] = Field(default_factory=list)
    target_article_section: str | None = None
    expected_evidence_type: NonEmptyText
    stopping_criteria: NonEmptyText
    language: NonEmptyText = "en"


class ArticleAnalysis(DomainModel):
    schema_version: ContractVersion = "1.0"
    title: str | None = None
    h1: str | None = None
    headings: list[str] = Field(default_factory=list)
    existing_claims: list[str] = Field(default_factory=list)
    images: list[str] = Field(default_factory=list)
    internal_links: list[str] = Field(default_factory=list)
    page_role: str | None = None
    first_hand_material: list[str] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)
    missing_user_questions: list[str] = Field(default_factory=list)
    evidence_gaps_by_lane: dict[str, list[str]] = Field(default_factory=dict)


class ResearchPlan(DomainModel):
    schema_version: ContractVersion = "1.0"
    research_id: Identifier
    request_hash: Sha256Digest
    mode: ResearchMode
    provider: NonEmptyText
    target_article_url: HttpUrl | None = None
    questions: list[ResearchQuestion] = Field(min_length=1)
    queries: list[ResearchQuery] = Field(min_length=1)
    source_lane_policies: list[SourceLanePolicy] = Field(min_length=1)
    article_analysis: ArticleAnalysis | None = None
    maximum_search_calls: int = Field(ge=1)
    maximum_sources: int = Field(ge=1)
    maximum_image_candidates: int = Field(ge=0)
    image_research_required: bool = False
    plan_hash: Sha256Digest | None = None


class SearchRun(DomainModel):
    schema_version: ContractVersion = "1.0"
    search_run_id: Identifier
    research_id: Identifier
    plan_hash: Sha256Digest
    provider: NonEmptyText
    query_ids: list[str]
    source_candidates: list[SourceCandidate] = Field(default_factory=list)
    image_candidates: list[ImageCandidate] = Field(default_factory=list)
    exclusions: list[dict[str, JsonValue]] = Field(default_factory=list)
    usage: dict[str, JsonValue] = Field(default_factory=dict)
    run_hash: Sha256Digest | None = None


class SourceCandidate(DomainModel):
    schema_version: ContractVersion = "1.0"
    source_id: Identifier
    query_id: Identifier
    provider: NonEmptyText
    source_url: HttpUrl
    normalized_url: HttpUrl
    source_lane: SourceLane
    title: str | None = None
    snippet: str | None = None
    published_at: AwareDatetime | None = None
    retrieved_at: AwareDatetime | None = None
    language: str | None = None
    domain: NonEmptyText
    has_images: bool = False
    image_urls: list[HttpUrl] = Field(default_factory=list)
    provider_rank: int | None = Field(default=None, ge=0)
    source_available: bool = True
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class SourceEvidenceRecord(DomainModel):
    schema_version: ContractVersion = "1.0"
    evidence_id: Identifier
    source_id: Identifier
    query_id: Identifier
    relevance: float = Field(ge=0, le=1)
    first_hand_status: Literal["first_hand", "hearsay", "mixed", "unknown"]
    specificity: float = Field(ge=0, le=1)
    commercial_promotion_risk: Literal["low", "medium", "high", "unknown"]
    source_access_quality: Literal["full", "partial", "snippet_only", "unavailable"]
    evidence_summary: NonEmptyText
    limitations: list[str] = Field(default_factory=list)
    proposed_topic_ids: list[str] = Field(default_factory=list)
    proposed_article_sections: list[str] = Field(default_factory=list)


class ImageCandidate(DomainModel):
    schema_version: ContractVersion = "1.0"
    image_id: Identifier
    source_id: Identifier
    query_id: Identifier
    image_url: HttpUrl
    normalized_image_url: HttpUrl
    source_page_url: HttpUrl
    alt_text: str | None = None
    caption: str | None = None
    brand: str | None = None
    model: str | None = None
    topic_ids: list[str] = Field(default_factory=list)
    publication_permission_status: PermissionStatus = PermissionStatus.UNKNOWN
    owner_review_status: ReviewStatus = ReviewStatus.PENDING
    linked_claim_ids: list[str] = Field(default_factory=list)
    perceptual_hash: str | None = None


class ImageEvidenceRecord(DomainModel):
    schema_version: ContractVersion = "1.0"
    image_evidence_id: Identifier
    image_id: Identifier
    source_id: Identifier
    observed_features: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    claim_ids: list[str] = Field(default_factory=list)
    provenance_proven: Literal[False] = False
    authentic_status_inferred: Literal[False] = False


class CandidateClaim(DomainModel):
    schema_version: ContractVersion = "1.0"
    claim_id: Identifier
    claim_text: NonEmptyText
    normalized_claim_text: NonEmptyText
    topic_ids: list[str] = Field(default_factory=list)
    brand_scope: list[str] = Field(default_factory=list)
    model_scope: list[str] = Field(default_factory=list)
    temporal_scope: TemporalScope = Field(default_factory=TemporalScope)
    proposed_article_sections: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class ClaimEvidenceLink(DomainModel):
    schema_version: ContractVersion = "1.0"
    link_id: Identifier
    claim_id: Identifier
    source_id: Identifier
    evidence_id: Identifier
    relationship: EvidenceRelationship
    independence_group: str | None = None
    rationale: NonEmptyText


class ClaimCluster(DomainModel):
    schema_version: ContractVersion = "1.0"
    cluster_id: Identifier
    canonical_claim_id: Identifier
    claim_ids: list[Identifier] = Field(min_length=1)
    supporting_source_ids: list[str] = Field(default_factory=list)
    contradicting_source_ids: list[str] = Field(default_factory=list)
    assessment: EvidenceAssessment
    source_lane_diversity: int = Field(ge=0)
    limitations: list[str] = Field(default_factory=list)


class ContradictionRecord(DomainModel):
    schema_version: ContractVersion = "1.0"
    contradiction_id: Identifier
    claim_ids: list[Identifier] = Field(min_length=2)
    source_ids: list[Identifier] = Field(min_length=2)
    position_a: NonEmptyText
    position_b: NonEmptyText
    possible_explanations: list[str] = Field(default_factory=list)
    resolution_status: Literal["unresolved", "scoped", "resolved"] = "unresolved"


class ArticleContentOpportunity(DomainModel):
    schema_version: ContractVersion = "1.0"
    opportunity_id: Identifier
    research_id: Identifier
    article_url: HttpUrl | None = None
    target_section: str | None = None
    opportunity_type: Literal[
        "add_evidence",
        "qualify_claim",
        "answer_question",
        "add_visual",
        "topic_only",
        "no_action",
    ]
    claim_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    rationale: NonEmptyText
    drafting_authorized: Literal[False] = False


class OwnerResearchDecision(DomainModel):
    schema_version: ContractVersion = "1.0"
    decision_id: Identifier
    subject_type: Literal["claim", "source", "image", "topic", "opportunity"]
    subject_id: Identifier
    decision: OwnerDecisionValue | None = None
    rationale: str = ""
    reviewer: str = ""
    reviewed_at: AwareDatetime | None = None


class ResearchSnapshot(DomainModel):
    schema_version: ContractVersion = "1.0"
    snapshot_id: Identifier
    research_id: Identifier
    request_hash: Sha256Digest
    plan_hash: Sha256Digest
    run_hash: Sha256Digest
    topic_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    claim_ids: list[str] = Field(default_factory=list)
    image_ids: list[str] = Field(default_factory=list)
    contradiction_ids: list[str] = Field(default_factory=list)
    opportunity_ids: list[str] = Field(default_factory=list)
    owner_decisions: list[OwnerResearchDecision] = Field(default_factory=list)
    source_availability: dict[str, bool] = Field(default_factory=dict)
    snapshot_hash: Sha256Digest | None = None


ResearchRequest = ArticleResearchRequest | TopicResearchRequest
