from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from reinaluxe_recovery.audit import (
    ArticleStructureAuditResult,
    AuditFinding,
    AuditRuleCode,
    AuditSeverity,
)


def test_finding_rejects_naive_datetime_and_unknown_fields() -> None:
    data = dict(
        finding_id=uuid4(),
        rule_code=AuditRuleCode.MISSING_H1,
        severity=AuditSeverity.WARNING,
        article_id=uuid4(),
        article_version_id=uuid4(),
        page_url="https://example.com/",
        message="Missing",
        evidence_refs=("sections",),
        created_at=datetime.now(),
        surprise=True,
    )
    with pytest.raises(ValidationError):
        AuditFinding(**data)


def test_counts_are_derived(article_version) -> None:
    finding = AuditFinding(
        finding_id=uuid4(),
        rule_code=AuditRuleCode.MISSING_H1,
        severity=AuditSeverity.WARNING,
        article_id=article_version.article.id,
        article_version_id=article_version.id,
        page_url=str(article_version.article.url),
        message="Missing",
        evidence_refs=("sections",),
        created_at=datetime.now(UTC),
    )
    result = ArticleStructureAuditResult(
        article_id=article_version.article.id,
        article_version_id=article_version.id,
        page_url=str(article_version.article.url),
        audited_at=datetime.now(UTC),
        rule_set_version="1.0",
        findings=(finding,),
        audited_fields=("sections",),
        finding_count=999,
    )
    assert result.finding_count == 1
    assert result.model_validate_json(result.model_dump_json()) == result
