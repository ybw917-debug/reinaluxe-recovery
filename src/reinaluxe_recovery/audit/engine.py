"""Deterministic audit engine and aggregation."""

from datetime import UTC, datetime

from reinaluxe_recovery.audit.contracts import (
    RULE_SET_VERSION,
    ArticleStructureAuditResult,
    AuditOptions,
    AuditSeverity,
    SiteStructureAuditResult,
)
from reinaluxe_recovery.audit.rules import audit_rules
from reinaluxe_recovery.persistence.dto import StoredArticleVersionSummary

AUDITED_FIELDS = (
    "title",
    "canonical_url",
    "meta_description",
    "sections",
    "schema_markup",
)
_SEVERITY_ORDER = {
    AuditSeverity.ERROR: 0,
    AuditSeverity.WARNING: 1,
    AuditSeverity.INFO: 2,
}


def audit_article(
    version: StoredArticleVersionSummary,
    inventory: frozenset[str],
    *,
    options: AuditOptions = AuditOptions(),
    audited_at: datetime | None = None,
) -> ArticleStructureAuditResult:
    moment = audited_at or datetime.now(UTC)
    findings = audit_rules(version.article, version.id, inventory, moment)
    findings = [
        f
        for f in findings
        if (options.include_info or f.severity is not AuditSeverity.INFO)
        and (options.rule_codes is None or f.rule_code in options.rule_codes)
    ]
    findings.sort(
        key=lambda f: (
            _SEVERITY_ORDER[f.severity],
            f.rule_code.value,
            f.field_path or "",
            str(f.finding_id),
        )
    )
    return ArticleStructureAuditResult(
        article_id=version.article.id,
        article_version_id=version.id,
        page_url=str(version.article.url),
        audited_at=moment,
        rule_set_version=RULE_SET_VERSION,
        findings=tuple(findings),
        audited_fields=AUDITED_FIELDS,
    )


def audit_article_versions(
    versions: list[StoredArticleVersionSummary],
    inventory: frozenset[str],
    *,
    options: AuditOptions = AuditOptions(),
    audited_at: datetime | None = None,
) -> list[ArticleStructureAuditResult]:
    moment = audited_at or datetime.now(UTC)
    results = [
        audit_article(v, inventory, options=options, audited_at=moment)
        for v in versions
    ]
    return sorted(results, key=lambda r: (r.page_url, str(r.article_version_id)))


def audit_latest_articles(
    versions: list[StoredArticleVersionSummary],
    inventory: frozenset[str],
    *,
    options: AuditOptions = AuditOptions(),
    audited_at: datetime | None = None,
) -> list[ArticleStructureAuditResult]:
    latest: dict[str, StoredArticleVersionSummary] = {}
    for version in versions:
        url = str(version.article.url)
        if url not in latest or version.version_number > latest[url].version_number:
            latest[url] = version
    return audit_article_versions(
        list(latest.values()), inventory, options=options, audited_at=audited_at
    )


def aggregate_site_audit(
    results: list[ArticleStructureAuditResult], *, audited_at: datetime | None = None
) -> SiteStructureAuditResult:
    moment = audited_at or (results[0].audited_at if results else datetime.now(UTC))
    return SiteStructureAuditResult(
        audited_at=moment,
        rule_set_version=RULE_SET_VERSION,
        article_results=tuple(
            sorted(results, key=lambda r: (r.page_url, str(r.article_version_id)))
        ),
    )
