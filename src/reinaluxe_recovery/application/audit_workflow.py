"""Read-only orchestration for persisted Article structure audits."""

from reinaluxe_recovery.audit import (
    AuditOptions,
    NoMatchingArticlesError,
    SiteStructureAuditResult,
    aggregate_site_audit,
    audit_article_versions,
)
from reinaluxe_recovery.persistence import PersistenceRepository, SessionFactory
from reinaluxe_recovery.persistence.url_normalization import normalize_page_url


class ArticleAuditWorkflow:
    """Select detached DTOs in one read session and audit them without writes."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def run(self, options: AuditOptions = AuditOptions()) -> SiteStructureAuditResult:
        with self._session_factory() as session:
            repository = PersistenceRepository(session)
            pages = repository.list_pages()
            inventory = frozenset(page.normalized_url for page in pages)
            versions = (
                repository.list_latest_articles()
                if options.latest_only
                else repository.list_all_article_versions()
            )
            if options.page_urls is not None:
                selected = {normalize_page_url(url) for url in options.page_urls}
                versions = [
                    version
                    for version in versions
                    if normalize_page_url(str(version.article.url)) in selected
                    or (
                        version.article.canonical_url is not None
                        and normalize_page_url(str(version.article.canonical_url))
                        in selected
                    )
                ]
            if options.limit is not None:
                versions = versions[: options.limit]
            if not versions:
                raise NoMatchingArticlesError("no matching persisted Article versions")
            results = audit_article_versions(versions, inventory, options=options)
            return aggregate_site_audit(results)
