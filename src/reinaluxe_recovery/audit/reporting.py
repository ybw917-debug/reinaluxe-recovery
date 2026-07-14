"""Human-readable audit reporting."""

from reinaluxe_recovery.audit.contracts import AuditSeverity, SiteStructureAuditResult


def render_site_audit(result: SiteStructureAuditResult) -> str:
    counts = ", ".join(
        f"{s.value}={result.severity_counts.get(s, 0)}" for s in AuditSeverity
    )
    lines = [
        f"Pages audited: {result.page_count}",
        f"Versions audited: {result.article_version_count}",
        f"Total findings: {result.total_findings}",
        f"Severity counts: {counts}",
    ]
    for article in result.article_results:
        lines.append(f"\n{article.page_url} ({article.article_version_id})")
        for finding in article.findings:
            lines.append(
                f"- [{finding.severity.value}] {finding.rule_code.value} at {finding.field_path or 'article'}: {finding.message}"
            )
    return "\n".join(lines)
