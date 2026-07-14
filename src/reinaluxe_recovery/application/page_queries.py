"""Application-level page inventory and detail queries."""

from pydantic import BaseModel, ConfigDict, Field

from reinaluxe_recovery.persistence import PersistenceRepository, SessionFactory
from reinaluxe_recovery.persistence.dto import (
    StoredArticleVersionSummary,
    StoredCrawlSummary,
    StoredImportWarningSummary,
    StoredPageInventorySummary,
)


class PageNotFoundError(LookupError):
    """Raised when a normalized page URL is absent from local storage."""


class QueryDTO(BaseModel):
    """Strict immutable base for application query results."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class CrawlWarningGroup(QueryDTO):
    """One crawl and its detached warning records."""

    crawl: StoredCrawlSummary
    warnings: list[StoredImportWarningSummary] = Field(default_factory=list)


class PageDetails(QueryDTO):
    """Page inventory, current Article, and optional history."""

    page: StoredPageInventorySummary
    latest_article: StoredArticleVersionSummary | None = None
    crawl_history: list[StoredCrawlSummary] = Field(default_factory=list)
    article_version_history: list[StoredArticleVersionSummary] = Field(
        default_factory=list
    )
    warnings_by_crawl: list[CrawlWarningGroup] = Field(default_factory=list)


class PageInventoryResult(QueryDTO):
    """Stable paginated page-list output contract."""

    items: list[StoredPageInventorySummary] = Field(default_factory=list)
    limit: int | None = Field(default=None, ge=1)
    offset: int = Field(ge=0)


class PageQueryService:
    """Open read sessions and return only Pydantic application DTOs."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def list_pages(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> PageInventoryResult:
        """Return deterministic, paginated page inventory."""
        with self._session_factory() as session:
            return PageInventoryResult(
                items=PersistenceRepository(session).list_page_inventory(
                    limit=limit,
                    offset=offset,
                ),
                limit=limit,
                offset=offset,
            )

    def show_page(self, url: str, *, include_history: bool = False) -> PageDetails:
        """Return one page and optionally all local crawl/version history."""
        with self._session_factory() as session:
            repository = PersistenceRepository(session)
            page = repository.get_page_inventory(url)
            if page is None:
                raise PageNotFoundError(f"page not found: {url}")
            latest = repository.get_latest_article(url)
            if not include_history:
                return PageDetails(page=page, latest_article=latest)
            crawls = repository.list_crawl_records(url)
            versions = repository.list_article_versions(url)
            warning_groups = [
                CrawlWarningGroup(
                    crawl=crawl,
                    warnings=repository.list_import_warnings(crawl.id),
                )
                for crawl in crawls
            ]
            return PageDetails(
                page=page,
                latest_article=latest,
                crawl_history=crawls,
                article_version_history=versions,
                warnings_by_crawl=warning_groups,
            )
