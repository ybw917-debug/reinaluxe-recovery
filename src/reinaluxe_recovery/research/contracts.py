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

from reinaluxe_recovery.community.normalization import content_hash, stable_id
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


class ContentProductionMode(StrEnum):
    RESEARCH_ONLY = "research_only"
    LEGACY_RECONSTRUCTION = "legacy_reconstruction"
    NEW_PAGE_BUILD = "new_page_build"


class PublicationIntensity(StrEnum):
    RESTRAINED = "restrained"
    ASSERTIVE = "assertive"
    HIGHLY_ASSERTIVE_BUT_SUPPORTABLE = "highly_assertive_but_supportable"


class EvidenceOwnershipClass(StrEnum):
    ORIGINAL_OWNER_EVIDENCE = "original_owner_evidence"
    OWNER_ANALYSIS_OF_EXTERNAL_EVIDENCE = "owner_analysis_of_external_evidence"
    OWNER_MARKET_SYNTHESIS = "owner_market_synthesis"
    ATTRIBUTED_COMMUNITY_REPORT = "attributed_community_report"
    ATTRIBUTED_SUPPLIER_CLAIM = "attributed_supplier_claim"
    AUTHORIZED_CLIENT_CASE = "authorized_client_case"
    DISCLOSED_COMPOSITE_CASE = "disclosed_composite_case"
    INTERNAL_ONLY_SOURCE = "internal_only_source"
    UNKNOWN_PERMISSION_SOURCE = "unknown_permission_source"


class ContentChangeOperation(StrEnum):
    KEEP = "KEEP"
    ENRICH = "ENRICH"
    REPLACE = "REPLACE"
    MOVE = "MOVE"
    SPLIT = "SPLIT"
    DELETE = "DELETE"
    ADD_BEFORE = "ADD_BEFORE"
    ADD_AFTER = "ADD_AFTER"


class ImageSourceCategory(StrEnum):
    EXISTING_PAGE_IMAGE = "existing_page_image"
    OWNER_ORIGINAL = "owner_original"
    OWNER_SUBMITTED = "owner_submitted"
    QC_IMAGE = "qc_image"
    SELLER_SHOT = "seller_shot"
    SUPPLIER_PROVIDED = "supplier_provided"
    COMMUNITY_IMAGE = "community_image"
    OFFICIAL_REFERENCE = "official_reference"
    EXPERT_REFERENCE = "expert_reference"
    COMMERCIAL_LISTING = "commercial_listing"
    UNKNOWN_ORIGIN = "unknown_origin"


class SmokeRecommendation(StrEnum):
    FULL_RUN_RECOMMENDED = "full_run_recommended"
    FULL_RUN_RECOMMENDED_WITH_ADJUSTMENTS = "full_run_recommended_with_adjustments"
    PROVIDER_COVERAGE_INSUFFICIENT = "provider_coverage_insufficient"
    CONFIGURATION_FAILED = "configuration_failed"
    ANALYSIS_FAILED = "analysis_failed"


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


class OwnerVoiceEvidence(DomainModel):
    schema_version: ContractVersion = "1.0"
    owner_reviewed: bool = False
    owner_compared: bool = False
    owner_analyzed: bool = False
    owner_sourcing_conversation: bool = False
    owner_physically_handled: bool = False
    owner_received_physical_item: bool = False
    owner_photographed: bool = False
    owner_measured: bool = False
    owner_used_long_term: bool = False
    authorized_client_case: bool = False


class FirstPersonEligibilityRecord(DomainModel):
    schema_version: ContractVersion = "1.0"
    eligibility_id: Identifier
    research_id: Identifier
    owner_reviewed: bool = False
    owner_compared: bool = False
    owner_analyzed: bool = False
    owner_sourcing_conversation: bool = False
    owner_physically_handled: bool = False
    owner_received_physical_item: bool = False
    owner_photographed: bool = False
    owner_measured: bool = False
    owner_used_long_term: bool = False
    authorized_client_case: bool = False
    permitted_first_person_phrases: list[str] = Field(default_factory=list)
    prohibited_first_person_phrases: list[str] = Field(default_factory=list)
    strongest_owner_voice_wording: NonEmptyText


class ExistingArticleImage(DomainModel):
    schema_version: ContractVersion = "1.0"
    image_id: Identifier
    source_url: NonEmptyText
    section_id: Identifier
    alt_text: str | None = None
    caption: str | None = None
    preserve: bool = True


class ExistingArticleSection(DomainModel):
    schema_version: ContractVersion = "1.0"
    section_id: Identifier
    order: int = Field(ge=0)
    heading_level: int = Field(ge=1, le=6)
    heading: NonEmptyText
    paragraphs: list[str] = Field(default_factory=list)
    image_ids: list[str] = Field(default_factory=list)
    internal_links: list[str] = Field(default_factory=list)
    distinctive_passages: list[str] = Field(default_factory=list)
    first_person_passages: list[str] = Field(default_factory=list)


class EditorialSynthesisRecord(DomainModel):
    schema_version: ContractVersion = "1.0"
    synthesis_id: Identifier
    research_id: Identifier
    claim_id: str | None = None
    research_question_id: str | None = None
    evidence_ownership_class: EvidenceOwnershipClass
    source_observation: NonEmptyText
    source_count: int = Field(ge=0)
    independent_source_cluster_count: int = Field(default=0, ge=0)
    source_lane_count: int = Field(ge=0)
    visual_evidence_count: int = Field(ge=0)
    contradiction_status: Literal["none", "present", "unresolved"]
    editorial_inference: NonEmptyText
    restrained_wording: NonEmptyText
    assertive_wording: NonEmptyText
    highly_assertive_but_supportable_wording: NonEmptyText
    publication_intensity_allowed: PublicationIntensity
    selected_publication_wording: NonEmptyText
    concise_limitation: NonEmptyText
    prohibited_unsupported_extension: NonEmptyText
    proposed_section: str | None = None
    narrative_value: NonEmptyText
    reader_usefulness: NonEmptyText
    conversion_value: NonEmptyText


class ContentTransformationRecord(DomainModel):
    schema_version: ContractVersion = "1.0"
    transformation_id: Identifier
    research_id: Identifier
    existing_section_id: str | None = None
    research_question_id: str | None = None
    supporting_source_ids: list[str] = Field(default_factory=list)
    relevant_image_ids: list[str] = Field(default_factory=list)
    source_observation: NonEmptyText
    editorial_inference: NonEmptyText
    publication_wording: NonEmptyText
    concise_limitation: NonEmptyText
    operation: ContentChangeOperation
    preserves_distinctive_content: bool = True
    preserves_existing_images: bool = True


class NewPageAssetRecord(DomainModel):
    schema_version: ContractVersion = "1.0"
    asset_id: Identifier
    asset_type: Literal["image", "text", "measurement", "document", "other"]
    local_path: Path | None = None
    relative_path: str | None = None
    remote_url: HttpUrl | None = None
    brand: str | None = None
    model: str | None = None
    size: str | None = None
    leather: str | None = None
    hardware: str | None = None
    description: str | None = None
    angle_or_detail: str | None = None
    source_category: ImageSourceCategory | None = None
    source_code: str | None = None
    owner_reviewed: bool = False
    owner_photographed: bool = False
    publication_permission: NonEmptyText = "unknown_permission"
    target_topics: list[str] = Field(default_factory=list)
    sha256: Sha256Digest | None = None
    perceptual_hash: str | None = None


class AssetManifestRecord(DomainModel):
    schema_version: ContractVersion = "1.0"
    asset_id: Identifier
    relative_path: Path
    file_type: NonEmptyText
    sha256: Sha256Digest
    perceptual_hash: str = ""
    brand: str = ""
    model: str = ""
    size: str = ""
    leather: str = ""
    hardware: str = ""
    angle_or_detail: str = ""
    source_category: ImageSourceCategory | None = None
    source_code: str = ""
    owner_reviewed: bool = False
    owner_photographed: bool = False
    publication_permission: str = ""
    target_topics: list[str] = Field(default_factory=list)
    notes: str = ""

    @model_validator(mode="after")
    def validate_local_owner_record(self) -> Self:
        if self.relative_path.is_absolute() or ".." in self.relative_path.parts:
            raise ValueError("asset relative_path must remain inside the asset root")
        if self.source_category is ImageSourceCategory.OWNER_ORIGINAL and not (
            self.owner_reviewed and self.owner_photographed
        ):
            raise ValueError(
                "owner_original requires explicit owner review and photography records"
            )
        return self


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
    content_production_mode: ContentProductionMode = ContentProductionMode.RESEARCH_ONLY
    publication_intensity: PublicationIntensity = (
        PublicationIntensity.HIGHLY_ASSERTIVE_BUT_SUPPORTABLE
    )
    preserve_existing_images: bool = False
    preserve_distinctive_content: bool = False
    owner_firsthand_evidence_required: bool = False
    maximum_new_sections: int = Field(default=0, ge=0)
    maximum_new_sections_explicitly_authorized: bool = False
    owner_voice_evidence: OwnerVoiceEvidence = Field(default_factory=OwnerVoiceEvidence)
    distinctive_content_requirements: list[str] = Field(default_factory=list)
    existing_image_requirements: list[str] = Field(default_factory=list)
    minimum_existing_image_count: int = Field(default=0, ge=0)
    asset_root: Path | None = None
    asset_manifest: Path | None = None
    search_intents: list[str] = Field(default_factory=list)
    research_database_path: Path | None = None
    request_hash: Sha256Digest | None = None

    @model_validator(mode="before")
    @classmethod
    def apply_production_defaults(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        mode = data.get("content_production_mode", ContentProductionMode.RESEARCH_ONLY)
        if (
            mode == ContentProductionMode.LEGACY_RECONSTRUCTION
            or mode == "legacy_reconstruction"
        ):
            data.setdefault("preserve_existing_images", True)
            data.setdefault("preserve_distinctive_content", True)
            data.setdefault("owner_firsthand_evidence_required", False)
            data.setdefault("maximum_new_sections", 3)
            data.setdefault(
                "publication_intensity",
                PublicationIntensity.HIGHLY_ASSERTIVE_BUT_SUPPORTABLE,
            )
        elif mode == ContentProductionMode.NEW_PAGE_BUILD or mode == "new_page_build":
            data.setdefault("owner_firsthand_evidence_required", False)
            data.setdefault("maximum_new_sections", 0)
        return data

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
        if (
            self.content_production_mode is ContentProductionMode.LEGACY_RECONSTRUCTION
            and self.maximum_new_sections > 3
            and not self.maximum_new_sections_explicitly_authorized
        ):
            raise ValueError(
                "legacy reconstruction allows at most three new sections unless explicitly authorized"
            )
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
        if self.content_production_mode is ContentProductionMode.NEW_PAGE_BUILD:
            raise ValueError("new_page_build requires a topic research request")
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
        if self.content_production_mode is ContentProductionMode.LEGACY_RECONSTRUCTION:
            raise ValueError(
                "legacy_reconstruction requires an article research request"
            )
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
    query_family: str | None = None
    source_lane: SourceLane
    requested_source_lane: SourceLane
    search_text: NonEmptyText
    exact_search_query: NonEmptyText
    search_domain_filter: str | None = None
    maximum_results: int = Field(default=10, ge=1, le=15)
    positive_terms: list[str] = Field(default_factory=list)
    exclusion_terms: list[str] = Field(default_factory=list)
    query_anchor_terms: list[str] = Field(default_factory=list)
    query_exclusion_terms: list[str] = Field(default_factory=list)
    required_topic_anchors: list[str] = Field(default_factory=list)
    prohibited_unrelated_entities: list[str] = Field(default_factory=list)
    article_entities_included: list[str] = Field(default_factory=list)
    entity_inclusion_rationale: str = "No article entities were included."
    query_generation_inputs: dict[str, JsonValue] = Field(default_factory=dict)
    clear_research_question: str | None = None
    query_hash: Sha256Digest = "0" * 64
    temporal_range: TemporalScope = Field(default_factory=TemporalScope)
    brand_scope: list[str] = Field(default_factory=list)
    model_scope: list[str] = Field(default_factory=list)
    target_article_section: str | None = None
    expected_evidence_type: NonEmptyText
    stopping_criteria: NonEmptyText
    language: NonEmptyText = "en"

    @model_validator(mode="before")
    @classmethod
    def preserve_query_integrity(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        exact = data.get("exact_search_query") or data.get("search_text")
        requested = data.get("requested_source_lane") or data.get("source_lane")
        anchors = data.get("query_anchor_terms") or data.get("positive_terms") or []
        exclusions = (
            data.get("query_exclusion_terms") or data.get("exclusion_terms") or []
        )
        data["search_text"] = exact
        data["exact_search_query"] = exact
        data["source_lane"] = requested
        data["requested_source_lane"] = requested
        data["positive_terms"] = list(anchors)
        data["query_anchor_terms"] = list(anchors)
        data["exclusion_terms"] = list(exclusions)
        data["query_exclusion_terms"] = list(exclusions)
        expected = content_hash(
            {
                "exact_search_query": exact,
                "query_family": data.get("query_family"),
                "requested_source_lane": requested,
                "search_domain_filter": data.get("search_domain_filter"),
                "query_anchor_terms": list(anchors),
                "query_exclusion_terms": list(exclusions),
                "target_article_section": data.get("target_article_section"),
                "article_entities_included": data.get("article_entities_included", []),
                "query_generation_inputs": data.get("query_generation_inputs", {}),
                "clear_research_question": data.get("clear_research_question"),
            }
        )
        supplied = data.get("query_hash")
        if supplied is not None and supplied != expected:
            raise ValueError("query_hash does not match query-generation inputs")
        data["query_hash"] = expected
        return data


class QueryQualityRecord(DomainModel):
    schema_version: ContractVersion = "1.0"
    query_id: Identifier
    passed: bool
    required_anchor_hits: list[str] = Field(default_factory=list)
    missing_required_anchors: list[str] = Field(default_factory=list)
    prohibited_entity_hits: list[str] = Field(default_factory=list)
    entity_contamination_score: float = Field(ge=0, le=1)
    lane_strategy_valid: bool
    duplicate_query_risk: bool
    research_question_lane_consistency: bool
    quoted_phrase_count: int = Field(ge=0)
    quoted_token_ratio: float = Field(ge=0, le=1)
    retrieval_overconstraint_risk: bool
    ambiguous_acronyms: list[str] = Field(default_factory=list)
    ambiguous_acronym_mitigated: bool
    natural_language_query_score: float = Field(ge=0, le=1)
    retrieval_quality_passed: bool
    failure_reasons: list[str] = Field(default_factory=list)


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
    existing_sections: list[ExistingArticleSection] = Field(default_factory=list)
    existing_images: list[ExistingArticleImage] = Field(default_factory=list)


class ResearchPlan(DomainModel):
    schema_version: ContractVersion = "1.0"
    research_id: Identifier
    request_hash: Sha256Digest
    mode: ResearchMode
    provider: NonEmptyText
    target_article_url: HttpUrl | None = None
    questions: list[ResearchQuestion] = Field(min_length=1)
    queries: list[ResearchQuery] = Field(default_factory=list)
    source_lane_policies: list[SourceLanePolicy] = Field(min_length=1)
    article_analysis: ArticleAnalysis | None = None
    maximum_search_calls: int = Field(ge=1)
    maximum_sources: int = Field(ge=1)
    maximum_image_candidates: int = Field(ge=0)
    image_research_required: bool = False
    content_production_mode: ContentProductionMode = ContentProductionMode.RESEARCH_ONLY
    publication_intensity: PublicationIntensity = (
        PublicationIntensity.HIGHLY_ASSERTIVE_BUT_SUPPORTABLE
    )
    preserve_existing_images: bool = False
    preserve_distinctive_content: bool = False
    owner_firsthand_evidence_required: bool = False
    maximum_new_sections: int = Field(default=0, ge=0)
    owner_voice_evidence: OwnerVoiceEvidence = Field(default_factory=OwnerVoiceEvidence)
    distinctive_content_requirements: list[str] = Field(default_factory=list)
    existing_image_requirements: list[str] = Field(default_factory=list)
    minimum_existing_image_count: int = Field(default=0, ge=0)
    asset_root: Path | None = None
    asset_manifest: Path | None = None
    search_intents: list[str] = Field(default_factory=list)
    research_database_path: Path | None = None
    reusable_topic_ids: list[str] = Field(default_factory=list)
    plan_hash: Sha256Digest | None = None

    @model_validator(mode="after")
    def require_queries_unless_reuse_is_sufficient(self) -> Self:
        if not self.queries and not (
            self.content_production_mode is ContentProductionMode.NEW_PAGE_BUILD
            and self.reusable_topic_ids
        ):
            raise ValueError(
                "research plan requires queries unless reusable new-page evidence is sufficient"
            )
        return self


class SearchRun(DomainModel):
    schema_version: ContractVersion = "1.0"
    search_run_id: Identifier
    research_id: Identifier
    plan_hash: Sha256Digest
    provider: NonEmptyText
    query_ids: list[str]
    queries: list[ResearchQuery] = Field(default_factory=list)
    source_candidates: list[SourceCandidate] = Field(default_factory=list)
    image_candidates: list[ImageCandidate] = Field(default_factory=list)
    visual_page_candidates: list[VisualPageCandidate] = Field(default_factory=list)
    exclusions: list[dict[str, JsonValue]] = Field(default_factory=list)
    usage: dict[str, JsonValue] = Field(default_factory=dict)
    run_hash: Sha256Digest | None = None


class SourceCandidate(DomainModel):
    schema_version: ContractVersion = "1.0"
    source_id: Identifier
    query_id: Identifier
    query_family: str | None = None
    provider: NonEmptyText
    provider_result_id: str | None = None
    provider_access_classification: Literal[
        "provider_returned_snippet", "provider_returned_content", "metadata_only"
    ] = "provider_returned_snippet"
    source_url: HttpUrl
    normalized_url: HttpUrl
    source_lane: SourceLane
    requested_source_lane: SourceLane
    classified_source_lane: SourceLane
    classification_rule: NonEmptyText
    classification_confidence: float = Field(ge=0, le=1)
    classification_override_status: Literal[
        "requested_lane_confirmed", "classified_lane_overridden", "legacy_record"
    ]
    title: str | None = None
    snippet: str | None = None
    published_at: AwareDatetime | None = None
    retrieved_at: AwareDatetime | None = None
    language: str | None = None
    domain: NonEmptyText
    exact_host: NonEmptyText
    registrable_domain: NonEmptyText
    organization_cluster_id: Identifier
    regional_variant: str | None = None
    independent_source_cluster_id: Identifier
    has_images: bool = False
    image_urls: list[HttpUrl] = Field(default_factory=list)
    provider_rank: int | None = Field(default=None, ge=0)
    source_cluster_id: str | None = None
    source_available: bool = True
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def preserve_lane_and_cluster_compatibility(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        classified = data.get("classified_source_lane") or data.get("source_lane")
        requested = data.get("requested_source_lane") or classified
        data["source_lane"] = classified
        data["classified_source_lane"] = classified
        data["requested_source_lane"] = requested
        data.setdefault("classification_rule", "legacy_record")
        data.setdefault("classification_confidence", 0.5)
        data.setdefault("classification_override_status", "legacy_record")
        host = data.get("exact_host") or data.get("domain") or "unknown.invalid"
        data["domain"] = host
        data["exact_host"] = host
        data.setdefault("registrable_domain", host)
        organization = data.get("organization_cluster_id") or stable_id(
            "organization", data["registrable_domain"]
        )
        independent = (
            data.get("independent_source_cluster_id")
            or data.get("source_cluster_id")
            or organization
        )
        data["organization_cluster_id"] = organization
        data["independent_source_cluster_id"] = independent
        data["source_cluster_id"] = independent
        return data


class SourceEvidenceRecord(DomainModel):
    schema_version: ContractVersion = "1.0"
    evidence_id: Identifier
    source_id: Identifier
    query_id: Identifier
    source_lane_classification: SourceLane | None = None
    relevance: float = Field(ge=0, le=1)
    first_hand_status: Literal["first_hand", "hearsay", "mixed", "unknown"]
    specificity: float = Field(ge=0, le=1)
    commercial_promotion_risk: Literal["low", "medium", "high", "unknown"]
    source_access_quality: Literal["full", "partial", "snippet_only", "unavailable"]
    evidence_summary: NonEmptyText
    key_observations: list[str] = Field(default_factory=list)
    image_presence_assessment: Literal[
        "present", "not_returned", "metadata_only", "uncertain"
    ] = "uncertain"
    limitations: list[str] = Field(default_factory=list)
    proposed_topic_ids: list[str] = Field(default_factory=list)
    proposed_article_sections: list[str] = Field(default_factory=list)


class ImageCandidate(DomainModel):
    schema_version: ContractVersion = "1.0"
    image_id: Identifier
    source_id: Identifier
    query_id: Identifier
    image_url: HttpUrl | None = None
    normalized_image_url: HttpUrl | None = None
    source_page_url: HttpUrl
    alt_text: str | None = None
    caption: str | None = None
    brand: str | None = None
    model: str | None = None
    size: str | None = None
    leather: str | None = None
    hardware: str | None = None
    target_topic: str | None = None
    proposed_article_section: str | None = None
    image_source_category: ImageSourceCategory = ImageSourceCategory.UNKNOWN_ORIGIN
    expected_visual_evidence: str | None = None
    required_attribution: str | None = None
    duplicate_check_status: Literal[
        "not_checked", "unique", "exact_duplicate", "probable_duplicate"
    ] = "not_checked"
    provider_media_metadata: dict[str, JsonValue] = Field(default_factory=dict)
    topic_ids: list[str] = Field(default_factory=list)
    publication_permission_status: PermissionStatus = PermissionStatus.UNKNOWN
    owner_review_status: ReviewStatus = ReviewStatus.PENDING
    linked_claim_ids: list[str] = Field(default_factory=list)
    perceptual_hash: str | None = None
    candidate_resolution_status: Literal["resolved_image_candidate"] = (
        "resolved_image_candidate"
    )
    image_locator_type: Literal[
        "provider_image_url",
        "explicit_media_asset_url",
        "existing_page_image_id",
        "local_file_path",
        "source_specific_metadata",
    ]
    image_locator: NonEmptyText
    page_may_contain_images: bool = True
    actual_image_reference_available: Literal[True] = True
    qualification_failure_reason: None = None
    existing_page_image_id: str | None = None
    local_file_path: Path | None = None

    @model_validator(mode="before")
    @classmethod
    def require_resolved_visual_reference(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        locator = data.get("image_locator")
        locator_type = data.get("image_locator_type")
        if not locator and data.get("image_url"):
            locator = str(data["image_url"])
            locator_type = "provider_image_url"
        elif not locator and data.get("existing_page_image_id"):
            locator = str(data["existing_page_image_id"])
            locator_type = "existing_page_image_id"
        elif not locator and data.get("local_file_path"):
            locator = str(data["local_file_path"])
            locator_type = "local_file_path"
        if not locator:
            metadata = data.get("provider_media_metadata")
            if isinstance(metadata, dict):
                for key in ("asset_url", "image_id", "asset_id", "src"):
                    candidate = metadata.get(key)
                    if candidate is not None and str(candidate).strip():
                        locator = str(candidate).strip()
                        locator_type = (
                            "explicit_media_asset_url"
                            if key in {"asset_url", "src"}
                            else "source_specific_metadata"
                        )
                        break
        if not locator or not locator_type:
            raise ValueError("resolved image candidate requires a real image locator")
        data["image_locator"] = locator
        data["image_locator_type"] = locator_type
        return data


class VisualPageCandidate(DomainModel):
    schema_version: ContractVersion = "1.0"
    visual_page_candidate_id: Identifier
    source_id: Identifier
    query_id: Identifier
    source_page_url: HttpUrl
    candidate_resolution_status: Literal["visual_page_candidate"] = (
        "visual_page_candidate"
    )
    image_locator_type: Literal["none"] = "none"
    image_locator: str = ""
    page_may_contain_images: bool = True
    actual_image_reference_available: Literal[False] = False
    qualification_failure_reason: NonEmptyText
    provider_media_metadata: dict[str, JsonValue] = Field(default_factory=dict)


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
