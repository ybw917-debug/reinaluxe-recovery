"""Atomic and idempotent persistence for validated offline imports."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from reinaluxe_recovery.importing import (
    ImportResult,
    ImportStatus,
    ImportWarning,
    ImportWarningSeverity,
)
from reinaluxe_recovery.persistence.database import (
    SessionFactory,
    transactional_session,
)
from reinaluxe_recovery.persistence.dto import (
    PersistDisposition,
    PersistImportResult,
)
from reinaluxe_recovery.persistence.enums import (
    StoredImportStatus,
    StoredWarningSeverity,
)
from reinaluxe_recovery.persistence.exceptions import (
    PersistenceConflictError,
    PersistenceContractError,
    PersistenceWriteError,
)
from reinaluxe_recovery.persistence.hashing import hash_normalized_article
from reinaluxe_recovery.persistence.models import (
    ArticleVersionModel,
    CrawlRecordModel,
    ImportWarningModel,
    PageIdentityModel,
    utc_now,
)
from reinaluxe_recovery.persistence.url_normalization import normalize_page_url


class ImportPersistenceService:
    """Persist each ImportResult as one all-or-nothing unit of work."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def save_import_result(self, import_result: ImportResult) -> PersistImportResult:
        """Persist a validated import safely and idempotently."""
        validated = self._validate_import_result(import_result)
        canonical_url = self._canonical_url(validated)
        content_hash = (
            hash_normalized_article(validated.article)
            if validated.article is not None
            else None
        )
        try:
            with transactional_session(self._session_factory) as session:
                return self._save(
                    session,
                    validated,
                    canonical_url,
                    content_hash,
                )
        except IntegrityError as error:
            raise PersistenceConflictError(
                "a concurrent import violated a persistence uniqueness constraint"
            ) from error
        except SQLAlchemyError as error:
            raise PersistenceWriteError(
                "import persistence transaction failed"
            ) from error

    def _save(
        self,
        session: Session,
        import_result: ImportResult,
        canonical_url: str,
        content_hash: str | None,
    ) -> PersistImportResult:
        fetched_at = import_result.snapshot.captured_at
        page = session.scalar(
            select(PageIdentityModel).where(
                PageIdentityModel.canonical_url == canonical_url
            )
        )
        page_disposition = PersistDisposition.REUSED
        if page is None:
            page = PageIdentityModel(
                canonical_url=canonical_url,
                normalized_url=canonical_url,
                first_seen_at=fetched_at,
                last_seen_at=fetched_at,
            )
            session.add(page)
            session.flush()
            page_disposition = PersistDisposition.CREATED
        else:
            self._update_observation_window(page, fetched_at)

        existing_crawl = session.scalar(
            select(CrawlRecordModel).where(
                CrawlRecordModel.page_id == page.id,
                CrawlRecordModel.fetched_at == fetched_at,
                CrawlRecordModel.source_html_hash == import_result.source_hash,
            )
        )
        if existing_crawl is not None:
            return self._reused_result(
                session,
                page,
                existing_crawl,
                import_result,
                canonical_url,
                content_hash,
            )

        crawl = self._new_crawl(page, import_result)
        session.add(crawl)
        session.flush()
        self._after_crawl_flush(session)
        warning_count = self._add_warnings(session, crawl, import_result.warnings)

        if import_result.status is ImportStatus.FAILED:
            session.flush()
            return PersistImportResult(
                page_id=page.id,
                crawl_id=crawl.id,
                page_disposition=page_disposition,
                crawl_disposition=PersistDisposition.CREATED,
                article_disposition=PersistDisposition.FAILED,
                canonical_url=canonical_url,
                source_hash=import_result.source_hash,
                warnings_persisted=warning_count,
                persisted_at=utc_now(),
                failure_message=self._failure_message(import_result),
            )

        assert import_result.article is not None
        assert content_hash is not None
        existing_article = session.scalar(
            select(ArticleVersionModel).where(
                ArticleVersionModel.page_id == page.id,
                ArticleVersionModel.normalized_content_hash == content_hash,
            )
        )
        if existing_article is not None:
            session.flush()
            return PersistImportResult(
                page_id=page.id,
                crawl_id=crawl.id,
                article_version_id=existing_article.id,
                page_disposition=page_disposition,
                crawl_disposition=PersistDisposition.CREATED,
                article_disposition=PersistDisposition.REUSED,
                article_version_number=existing_article.version_number,
                canonical_url=canonical_url,
                source_hash=import_result.source_hash,
                normalized_content_hash=content_hash,
                warnings_persisted=warning_count,
                persisted_at=utc_now(),
            )

        version_number = (
            session.scalar(
                select(func.max(ArticleVersionModel.version_number)).where(
                    ArticleVersionModel.page_id == page.id
                )
            )
            or 0
        ) + 1
        article = ArticleVersionModel(
            page_id=page.id,
            crawl_id=crawl.id,
            normalized_article_json=import_result.article.model_dump(mode="json"),
            normalized_content_hash=content_hash,
            version_number=version_number,
            published_at=import_result.article.published_at,
            modified_at=import_result.article.modified_at,
        )
        session.add(article)
        session.flush()
        self._after_article_flush(session)
        page.current_article_version_id = article.id
        session.flush()
        return PersistImportResult(
            page_id=page.id,
            crawl_id=crawl.id,
            article_version_id=article.id,
            page_disposition=page_disposition,
            crawl_disposition=PersistDisposition.CREATED,
            article_disposition=(
                PersistDisposition.CREATED
                if version_number == 1
                else PersistDisposition.VERSION_CREATED
            ),
            article_version_number=version_number,
            canonical_url=canonical_url,
            source_hash=import_result.source_hash,
            normalized_content_hash=content_hash,
            warnings_persisted=warning_count,
            persisted_at=utc_now(),
        )

    def _reused_result(
        self,
        session: Session,
        page: PageIdentityModel,
        crawl: CrawlRecordModel,
        import_result: ImportResult,
        canonical_url: str,
        content_hash: str | None,
    ) -> PersistImportResult:
        warning_count = (
            session.scalar(
                select(func.count(ImportWarningModel.id)).where(
                    ImportWarningModel.crawl_id == crawl.id
                )
            )
            or 0
        )
        article = None
        if content_hash is not None:
            article = session.scalar(
                select(ArticleVersionModel).where(
                    ArticleVersionModel.page_id == page.id,
                    ArticleVersionModel.normalized_content_hash == content_hash,
                )
            )
            if article is None:
                raise PersistenceWriteError(
                    "an idempotent successful crawl has no stored Article version"
                )
        return PersistImportResult(
            page_id=page.id,
            crawl_id=crawl.id,
            article_version_id=article.id if article is not None else None,
            page_disposition=PersistDisposition.REUSED,
            crawl_disposition=PersistDisposition.REUSED,
            article_disposition=(
                PersistDisposition.REUSED
                if article is not None
                else PersistDisposition.FAILED
            ),
            article_version_number=(
                article.version_number if article is not None else None
            ),
            canonical_url=canonical_url,
            source_hash=import_result.source_hash,
            normalized_content_hash=content_hash,
            warnings_persisted=warning_count,
            persisted_at=utc_now(),
            failure_message=(
                self._failure_message(import_result)
                if import_result.status is ImportStatus.FAILED
                else None
            ),
        )

    @staticmethod
    def _validate_import_result(import_result: ImportResult) -> ImportResult:
        try:
            validated = ImportResult.model_validate(import_result.model_dump())
        except (AttributeError, ValueError) as error:
            raise PersistenceContractError(
                "save_import_result requires a valid ImportResult"
            ) from error
        if (
            validated.snapshot.content_hash is not None
            and validated.snapshot.content_hash != validated.source_hash
        ):
            raise PersistenceContractError(
                "snapshot content_hash must match ImportResult source_hash"
            )
        if validated.article is not None:
            if validated.article.source_snapshot_id != validated.snapshot.id:
                raise PersistenceContractError(
                    "Article source_snapshot_id must reference the imported snapshot"
                )
            if (
                validated.article.source_content_hash is not None
                and validated.article.source_content_hash != validated.source_hash
            ):
                raise PersistenceContractError(
                    "Article source_content_hash must match ImportResult source_hash"
                )
        return validated

    @staticmethod
    def _canonical_url(import_result: ImportResult) -> str:
        if import_result.article is not None:
            candidate = import_result.article.canonical_url or import_result.article.url
        else:
            candidate = (
                import_result.snapshot.observed_canonical_url
                or import_result.snapshot.final_url
                or import_result.snapshot.requested_url
            )
        return normalize_page_url(str(candidate))

    @staticmethod
    def _update_observation_window(
        page: PageIdentityModel,
        fetched_at: datetime,
    ) -> None:
        if fetched_at < page.first_seen_at:
            page.first_seen_at = fetched_at
        if fetched_at > page.last_seen_at:
            page.last_seen_at = fetched_at

    @staticmethod
    def _new_crawl(
        page: PageIdentityModel,
        import_result: ImportResult,
    ) -> CrawlRecordModel:
        fatal_diagnostics = [
            warning.model_dump(mode="json")
            for warning in import_result.warnings
            if warning.severity is ImportWarningSeverity.FATAL
        ]
        return CrawlRecordModel(
            page_id=page.id,
            fetched_at=import_result.snapshot.captured_at,
            status_code=import_result.snapshot.http_status,
            response_headers=import_result.snapshot.response_headers,
            source_html_hash=import_result.source_hash,
            raw_html=import_result.snapshot.raw_html,
            import_status=(
                StoredImportStatus.SUCCEEDED
                if import_result.status is ImportStatus.SUCCEEDED
                else StoredImportStatus.FAILED
            ),
            fatal_diagnostics=fatal_diagnostics,
        )

    @staticmethod
    def _add_warnings(
        session: Session,
        crawl: CrawlRecordModel,
        warnings: list[ImportWarning],
    ) -> int:
        for warning in warnings:
            session.add(
                ImportWarningModel(
                    crawl_id=crawl.id,
                    warning_code=warning.code.value,
                    message=warning.message,
                    severity=StoredWarningSeverity(warning.severity.value),
                    source_location=warning.location,
                )
            )
        return len(warnings)

    @staticmethod
    def _failure_message(import_result: ImportResult) -> str:
        messages = [
            warning.message
            for warning in import_result.warnings
            if warning.severity is ImportWarningSeverity.FATAL
        ]
        return "; ".join(messages) or "Offline import failed without fatal diagnostics."

    def _after_crawl_flush(self, session: Session) -> None:
        """Internal test seam after crawl creation and before Article creation."""
        del session

    def _after_article_flush(self, session: Session) -> None:
        """Internal test seam before the current-version pointer is updated."""
        del session
