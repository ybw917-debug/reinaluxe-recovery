from reinaluxe_recovery.audit import (
    aggregate_site_audit,
    audit_article,
    render_site_audit,
)


def test_human_report(article_version) -> None:
    rendered = render_site_audit(
        aggregate_site_audit([audit_article(article_version, frozenset())])
    )
    assert "Pages audited: 1" in rendered
    assert "meta_description_too_short" in rendered
