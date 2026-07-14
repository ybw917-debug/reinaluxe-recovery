from datetime import UTC, datetime

from reinaluxe_recovery.audit import AuditRuleCode
from reinaluxe_recovery.audit.rules import audit_rules


def test_transparent_rules(article_version) -> None:
    findings = audit_rules(
        article_version.article,
        article_version.id,
        frozenset({"https://example.com/a"}),
        datetime.now(UTC),
    )
    codes = {finding.rule_code for finding in findings}
    assert AuditRuleCode.TITLE_H1_MISMATCH_CANDIDATE in codes
    assert AuditRuleCode.META_DESCRIPTION_TOO_SHORT in codes
    assert AuditRuleCode.VERY_SHORT_PARAGRAPH in codes
    assert AuditRuleCode.UNUSUALLY_LOW_WORD_COUNT in codes
    assert all("penalty" not in finding.message.casefold() for finding in findings)
    assert all("probability" not in finding.message.casefold() for finding in findings)
