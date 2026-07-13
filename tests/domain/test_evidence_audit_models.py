"""Tests for evidence, assessment, and recommendation contracts."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from reinaluxe_recovery.domain import (
    ClaimVerificationStatus,
    CommunityClaim,
    ContentRiskAssessment,
    EvidenceConfidence,
    EvidenceReference,
    EvidenceSourceType,
    RecoveryAction,
    RecoveryRecommendation,
    RiskCategory,
    RiskLevel,
)

NOW = datetime(2026, 7, 14, 10, 0, tzinfo=UTC)


def _evidence(article_id: UUID) -> EvidenceReference:
    return EvidenceReference(
        source_type=EvidenceSourceType.CRAWL_SNAPSHOT,
        source_name="crawl snapshot",
        supports="A repeated introduction was observed in source content.",
        observed_at=NOW,
        collected_at=NOW,
        confidence=EvidenceConfidence.HIGH,
        source_record_id="snapshot-001",
        related_article_ids=[article_id],
    )


def test_valid_evidence_reference_creation() -> None:
    """Factual evidence has a typed source, locator, and timestamp."""
    evidence = _evidence(uuid4())

    assert evidence.source_type is EvidenceSourceType.CRAWL_SNAPSHOT
    assert evidence.confidence is EvidenceConfidence.HIGH


def test_community_claims_are_separate_from_verified_evidence() -> None:
    """Community claims cannot receive factual-evidence confidence fields."""
    claim_data = {
        "statement": "Readers may prefer more close-up photographs.",
        "source_platform": "community_forum",
        "collected_at": NOW,
        "verification_status": ClaimVerificationStatus.UNVERIFIED,
        "source_record_id": "community-001",
        "confidence": EvidenceConfidence.VERIFIED,
    }

    with pytest.raises(ValidationError):
        CommunityClaim.model_validate(claim_data)

    with pytest.raises(ValidationError):
        EvidenceReference.model_validate(
            {
                "source_type": "community",
                "source_name": "community forum",
                "supports": "A community statement.",
                "observed_at": NOW,
                "collected_at": NOW,
                "confidence": "verified",
                "source_record_id": "community-001",
            }
        )


def test_valid_content_risk_assessment() -> None:
    """An assessment references evidence without claiming a causal penalty."""
    article_id = uuid4()
    evidence = _evidence(article_id)
    assessment = ContentRiskAssessment(
        article_id=article_id,
        assessed_at=NOW,
        risk_level=RiskLevel.HIGH,
        categories=[RiskCategory.STRUCTURAL_REPETITION],
        summary="Repeated structure warrants editorial review.",
        assessor="unit-test",
        evidence_reference_ids=[evidence.id],
        limitations=["No causal ranking conclusion is supported."],
    )

    assert assessment.risk_level is RiskLevel.HIGH
    assert assessment.evidence_reference_ids == [evidence.id]


def test_valid_recovery_recommendation() -> None:
    """A generated recommendation remains subject to human approval."""
    article_id = uuid4()
    evidence = _evidence(article_id)
    assessment_id = uuid4()
    recommendation = RecoveryRecommendation(
        article_id=article_id,
        assessment_id=assessment_id,
        action=RecoveryAction.REWRITE,
        created_at=NOW,
        rationale="Differentiate the introduction and preserve sourced details.",
        priority=RiskLevel.HIGH,
        evidence_reference_ids=[evidence.id],
    )

    assert recommendation.action is RecoveryAction.REWRITE
    assert recommendation.requires_human_review is True
