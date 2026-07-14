"""Read-only repositories returning detached Pydantic persistence DTOs."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from reinaluxe_recovery.domain import Article
from reinaluxe_recovery.persistence.dto import (
    StoredArticleVersionSummary,
    StoredCrawlSummary,
    StoredImportWarningSummary,
    StoredPageInventorySummary,
    StoredPageSummary,
)
from reinaluxe_recovery.persistence.exceptions import PersistenceQueryError
from reinaluxe_recovery.persistence.models import (
    ArticleVersionModel,
    CrawlRecordModel,
    ImportWarningModel,
    PageIdentityModel,
)
from reinaluxe_recovery.persistence.url_normalization import normalize_page_url

_ModelT = TypeVar("_ModelT")


def _page_dto(model: PageIdentityModel) -> StoredPageSummary:
    return StoredPageSummary(
        id=model.id,
        canonical_url=model.canonical_url,
        normalized_url=model.normalized_url,
        first_seen_at=model.first_seen_at,
        last_seen_at=model.last_seen_at,
        current_article_version_id=model.current_article_version_id,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _crawl_dto(model: CrawlRecordModel) -> StoredCrawlSummary:
    return StoredCrawlSummary(
        id=model.id,
        page_id=model.page_id,
        fetched_at=model.fetched_at,
        status_code=model.status_code,
        response_headers=model.response_headers,
        source_hash=model.source_html_hash,
        import_status=model.import_status,
        fatal_diagnostics=model.fatal_diagnostics,
        created_at=model.created_at,
    )


def _article_dto(model: ArticleVersionModel) -> StoredArticleVersionSummary:
    return StoredArticleVersionSummary(
        id=model.id,
        page_id=model.page_id,
        crawl_id=model.crawl_id,
        article=Article.model_validate(model.normalized_article_json),
        normalized_content_hash=model.normalized_content_hash,
        version_number=model.version_number,
        published_at=model.published_at,
        modified_at=model.modified_at,
        created_at=model.created_at,
    )


def _warning_dto(model: ImportWarningModel) -> StoredImportWarningSummary:
    return StoredImportWarningSummary(
        id=model.id,
        crawl_id=model.crawl_id,
        code=model.warning_code,
        message=model.message,
        severity=model.severity,
        field_path=model.field_path,
        source_location=model.source_location,
        created_at=model.created_at,
    )


class PersistenceRepository:
    """Queries within a caller-owned session; never commits transactions."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_page_by_url(self, url: str) -> StoredPageSummary | None:
        """Return the page identified by a normalized HTTP(S) URL."""
        normalized_url = normalize_page_url(url)
        model = self._scalar(
            select(PageIdentityModel).where(
                PageIdentityModel.canonical_url == normalized_url
            )
        )
        return _page_dto(model) if model is not None else None

    def get_page_by_id(self, page_id: UUID) -> StoredPageSummary | None:
        """Return a page by its durable identifier."""
        try:
            model = self._session.get(PageIdentityModel, page_id)
        except SQLAlchemyError as error:
            raise PersistenceQueryError("failed to read page identity") from error
        return _page_dto(model) if model is not None else None

    def list_pages(self) -> list[StoredPageSummary]:
        """Return every page in deterministic URL order."""
        models = self._scalars(
            select(PageIdentityModel).order_by(PageIdentityModel.canonical_url)
        )
        return [_page_dto(model) for model in models]

    def list_page_inventory(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[StoredPageInventorySummary]:
        """Return deterministic page inventory with aggregate history counts."""
        if limit is not None and limit < 1:
            raise ValueError("limit must be at least 1")
        if offset < 0:
            raise ValueError("offset must be non-negative")
        statement = select(PageIdentityModel).order_by(PageIdentityModel.canonical_url)
        if offset:
            statement = statement.offset(offset)
        if limit is not None:
            statement = statement.limit(limit)
        return [self._inventory_dto(model) for model in self._scalars(statement)]

    def get_page_inventory(self, url: str) -> StoredPageInventorySummary | None:
        """Return one page with aggregate crawl and version counts."""
        normalized_url = normalize_page_url(url)
        model = self._scalar(
            select(PageIdentityModel).where(
                PageIdentityModel.canonical_url == normalized_url
            )
        )
        return self._inventory_dto(model) if model is not None else None

    def get_crawl_record(self, crawl_id: UUID) -> StoredCrawlSummary | None:
        """Return one crawl observation by identifier."""
        try:
            model = self._session.get(CrawlRecordModel, crawl_id)
        except SQLAlchemyError as error:
            raise PersistenceQueryError("failed to read crawl record") from error
        return _crawl_dto(model) if model is not None else None

    def list_crawl_records(self, url: str) -> list[StoredCrawlSummary]:
        """Return newest-first crawl history for one canonical page."""
        normalized_url = normalize_page_url(url)
        models = self._scalars(
            select(CrawlRecordModel)
            .join(PageIdentityModel, CrawlRecordModel.page_id == PageIdentityModel.id)
            .where(PageIdentityModel.canonical_url == normalized_url)
            .order_by(CrawlRecordModel.fetched_at.desc(), CrawlRecordModel.id)
        )
        return [_crawl_dto(model) for model in models]

    def get_latest_article(self, url: str) -> StoredArticleVersionSummary | None:
        """Return the Article referenced by the page's current pointer."""
        normalized_url = normalize_page_url(url)
        model = self._scalar(
            select(ArticleVersionModel)
            .join(
                PageIdentityModel,
                PageIdentityModel.current_article_version_id == ArticleVersionModel.id,
            )
            .where(PageIdentityModel.canonical_url == normalized_url)
        )
        return _article_dto(model) if model is not None else None

    def list_article_versions(
        self,
        url: str,
    ) -> list[StoredArticleVersionSummary]:
        """Return oldest-first immutable Article history for one page."""
        normalized_url = normalize_page_url(url)
        models = self._scalars(
            select(ArticleVersionModel)
            .join(
                PageIdentityModel, ArticleVersionModel.page_id == PageIdentityModel.id
            )
            .where(PageIdentityModel.canonical_url == normalized_url)
            .order_by(ArticleVersionModel.version_number)
        )
        return [_article_dto(model) for model in models]

    def get_article_version(
        self,
        version_id: UUID,
    ) -> StoredArticleVersionSummary | None:
        """Return one validated stored Article version by identifier."""
        try:
            model = self._session.get(ArticleVersionModel, version_id)
        except SQLAlchemyError as error:
            raise PersistenceQueryError("failed to read article version") from error
        return _article_dto(model) if model is not None else None

    def list_import_warnings(
        self,
        crawl_id: UUID,
    ) -> list[StoredImportWarningSummary]:
        """Return diagnostics for one crawl in insertion order."""
        models = self._scalars(
            select(ImportWarningModel)
            .where(ImportWarningModel.crawl_id == crawl_id)
            .order_by(ImportWarningModel.created_at, ImportWarningModel.id)
        )
        return [_warning_dto(model) for model in models]

    def database_health_check(self) -> bool:
        """Confirm that the existing session can execute a local query."""
        try:
            return bool(self._session.scalar(select(1)) == 1)
        except SQLAlchemyError as error:
            raise PersistenceQueryError("database health check failed") from error

    def _inventory_dto(
        self,
        model: PageIdentityModel,
    ) -> StoredPageInventorySummary:
        try:
            crawl_count = (
                self._session.scalar(
                    select(func.count(CrawlRecordModel.id)).where(
                        CrawlRecordModel.page_id == model.id
                    )
                )
                or 0
            )
            version_count = (
                self._session.scalar(
                    select(func.count(ArticleVersionModel.id)).where(
                        ArticleVersionModel.page_id == model.id
                    )
                )
                or 0
            )
            current_version = None
            if model.current_article_version_id is not None:
                current_version = self._session.scalar(
                    select(ArticleVersionModel.version_number).where(
                        ArticleVersionModel.id == model.current_article_version_id
                    )
                )
        except SQLAlchemyError as error:
            raise PersistenceQueryError("failed to read page inventory") from error
        return StoredPageInventorySummary(
            id=model.id,
            canonical_url=model.canonical_url,
            current_article_version_id=model.current_article_version_id,
            current_version_number=current_version,
            first_seen_at=model.first_seen_at,
            last_seen_at=model.last_seen_at,
            crawl_count=crawl_count,
            article_version_count=version_count,
        )

    def _scalar(self, statement: Select[tuple[_ModelT]]) -> _ModelT | None:
        try:
            return self._session.scalars(statement).one_or_none()
        except SQLAlchemyError as error:
            raise PersistenceQueryError("persistence query failed") from error

    def _scalars(self, statement: Select[tuple[_ModelT]]) -> Sequence[_ModelT]:
        try:
            return self._session.scalars(statement).all()
        except SQLAlchemyError as error:
            raise PersistenceQueryError("persistence query failed") from error
