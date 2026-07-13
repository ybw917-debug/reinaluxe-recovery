"""Derived audit findings, assessments, and recommendation contracts."""

from typing import Literal, Self
from uuid import UUID, uuid4

from pydantic import AwareDatetime, Field, model_validator

from reinaluxe_recovery.domain.base import DomainModel, NonEmptyText
from reinaluxe_recovery.domain.enums import (
    RecoveryAction,
    RiskCategory,
    RiskLevel,
    SimilarityScope,
)
from reinaluxe_recovery.domain.evidence import (
    CommunityClaim,
    EvidenceReference,
    HumanReviewDecision,
)


def _require_known_ids(
    referenced_ids: list[UUID],
    available_ids: set[UUID],
    field_name: str,
) -> None:
    """Reject dangling references inside an audit result contract."""
    unknown_ids = set(referenced_ids) - available_ids
    if unknown_ids:
        unknown = ", ".join(sorted(str(item) for item in unknown_ids))
        raise ValueError(f"{field_name} contains unknown IDs: {unknown}")


class SimilarityFinding(DomainModel):
    """Evidence-backed overlap observation produced by an external method."""

    id: UUID = Field(default_factory=uuid4)
    subject_article_id: UUID
    compared_article_id: UUID
    scope: SimilarityScope
    observed_at: AwareDatetime
    summary: NonEmptyText
    method_name: NonEmptyText
    evidence_reference_ids: list[UUID] = Field(min_length=1)
    method_version: str | None = Field(default=None, max_length=100)
    similarity_score: float | None = Field(default=None, ge=0, le=1)
    subject_section_ids: list[UUID] = Field(default_factory=list)
    compared_section_ids: list[UUID] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_articles(self) -> Self:
        """Require a comparison between two distinct articles."""
        if self.subject_article_id == self.compared_article_id:
            raise ValueError("similarity finding requires two distinct articles")
        return self


class ContentRiskAssessment(DomainModel):
    """Automated, evidence-backed assessment that is not an owner decision."""

    id: UUID = Field(default_factory=uuid4)
    article_id: UUID
    assessed_at: AwareDatetime
    risk_level: RiskLevel
    categories: list[RiskCategory] = Field(min_length=1)
    summary: NonEmptyText
    assessor: NonEmptyText
    evidence_reference_ids: list[UUID] = Field(min_length=1)
    similarity_finding_ids: list[UUID] = Field(default_factory=list)
    community_claim_ids: list[UUID] = Field(default_factory=list)
    methodology_version: str | None = Field(default=None, max_length=100)
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_categories(self) -> Self:
        """Require unique controlled risk categories."""
        if len(self.categories) != len(set(self.categories)):
            raise ValueError("risk categories must be unique")
        return self


class RecoveryRecommendation(DomainModel):
    """Generated editorial proposal that always requires human review."""

    id: UUID = Field(default_factory=uuid4)
    article_id: UUID
    assessment_id: UUID
    action: RecoveryAction
    created_at: AwareDatetime
    rationale: NonEmptyText
    priority: RiskLevel
    evidence_reference_ids: list[UUID] = Field(min_length=1)
    requires_human_review: Literal[True] = True
    target_article_ids: list[UUID] = Field(default_factory=list)
    proposed_changes: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    expires_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_targets(self) -> Self:
        """Validate merge targets without deciding which pages should merge."""
        if len(self.target_article_ids) != len(set(self.target_article_ids)):
            raise ValueError("target_article_ids must be unique")
        if self.article_id in self.target_article_ids:
            raise ValueError("an article cannot target itself")
        if self.action is RecoveryAction.MERGE and not self.target_article_ids:
            raise ValueError("merge recommendations require target_article_ids")
        if self.expires_at is not None and self.expires_at < self.created_at:
            raise ValueError("expires_at must not precede created_at")
        return self


class ContentAuditResult(DomainModel):
    """Output envelope preserving distinct evidence, claims, and judgments."""

    contract_version: Literal["1.0"] = "1.0"
    id: UUID = Field(default_factory=uuid4)
    article_id: UUID
    generated_at: AwareDatetime
    evidence_references: list[EvidenceReference] = Field(min_length=1)
    risk_assessment: ContentRiskAssessment
    recovery_recommendations: list[RecoveryRecommendation] = Field(min_length=1)
    community_claims: list[CommunityClaim] = Field(default_factory=list)
    similarity_findings: list[SimilarityFinding] = Field(default_factory=list)
    human_review_decisions: list[HumanReviewDecision] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_references(self) -> Self:
        """Ensure all provenance references resolve within the output envelope."""
        evidence_ids = {item.id for item in self.evidence_references}
        claim_ids = {item.id for item in self.community_claims}
        finding_ids = {item.id for item in self.similarity_findings}
        recommendation_ids = {item.id for item in self.recovery_recommendations}

        if len(evidence_ids) != len(self.evidence_references):
            raise ValueError("evidence reference IDs must be unique")
        if len(claim_ids) != len(self.community_claims):
            raise ValueError("community claim IDs must be unique")
        if len(finding_ids) != len(self.similarity_findings):
            raise ValueError("similarity finding IDs must be unique")
        if len(recommendation_ids) != len(self.recovery_recommendations):
            raise ValueError("recovery recommendation IDs must be unique")

        assessment = self.risk_assessment
        if assessment.article_id != self.article_id:
            raise ValueError("risk assessment article_id must match audit article_id")
        _require_known_ids(
            assessment.evidence_reference_ids,
            evidence_ids,
            "risk_assessment.evidence_reference_ids",
        )
        _require_known_ids(
            assessment.community_claim_ids,
            claim_ids,
            "risk_assessment.community_claim_ids",
        )
        _require_known_ids(
            assessment.similarity_finding_ids,
            finding_ids,
            "risk_assessment.similarity_finding_ids",
        )

        for finding in self.similarity_findings:
            if finding.subject_article_id != self.article_id:
                raise ValueError("similarity finding subject must match audit article")
            _require_known_ids(
                finding.evidence_reference_ids,
                evidence_ids,
                "similarity_finding.evidence_reference_ids",
            )

        for recommendation in self.recovery_recommendations:
            if recommendation.article_id != self.article_id:
                raise ValueError(
                    "recommendation article_id must match audit article_id"
                )
            if recommendation.assessment_id != assessment.id:
                raise ValueError("recommendation assessment_id must match assessment")
            _require_known_ids(
                recommendation.evidence_reference_ids,
                evidence_ids,
                "recommendation.evidence_reference_ids",
            )

        for decision in self.human_review_decisions:
            if decision.article_id != self.article_id:
                raise ValueError(
                    "review decision article_id must match audit article_id"
                )
            if (
                decision.recommendation_id is not None
                and decision.recommendation_id not in recommendation_ids
            ):
                raise ValueError("review decision references an unknown recommendation")
            _require_known_ids(
                decision.evidence_reference_ids,
                evidence_ids,
                "review_decision.evidence_reference_ids",
            )
            _require_known_ids(
                decision.community_claim_ids,
                claim_ids,
                "review_decision.community_claim_ids",
            )
        return self
