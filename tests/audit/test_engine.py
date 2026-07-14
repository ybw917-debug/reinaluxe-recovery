from reinaluxe_recovery.audit import (
    AuditOptions,
    AuditSeverity,
    aggregate_site_audit,
    audit_article,
)


def test_filtering_and_aggregation_are_derived(article_version) -> None:
    result = audit_article(
        article_version, frozenset(), options=AuditOptions(include_info=False)
    )
    assert all(item.severity is not AuditSeverity.INFO for item in result.findings)
    site = aggregate_site_audit([result])
    assert site.page_count == 1
    assert site.article_version_count == 1
    assert site.total_findings == len(result.findings)
