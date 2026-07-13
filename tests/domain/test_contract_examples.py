"""Tests that published JSON examples match the executable contracts."""

from pathlib import Path

from reinaluxe_recovery.domain import Article, ContentAuditResult

EXAMPLES_DIR = Path(__file__).parents[2] / "docs" / "examples"


def test_normalized_article_example_round_trip() -> None:
    """The normalized article example survives JSON serialization."""
    article = Article.model_validate_json(
        (EXAMPLES_DIR / "normalized-article.json").read_text(encoding="utf-8")
    )

    restored = Article.model_validate_json(article.model_dump_json())

    assert restored == article


def test_content_audit_result_example_round_trip() -> None:
    """The audit example preserves evidence and recommendation references."""
    result = ContentAuditResult.model_validate_json(
        (EXAMPLES_DIR / "content-audit-result.json").read_text(encoding="utf-8")
    )

    restored = ContentAuditResult.model_validate_json(result.model_dump_json())

    assert restored == result
    assert restored.risk_assessment.evidence_reference_ids
    assert restored.recovery_recommendations[0].requires_human_review is True
