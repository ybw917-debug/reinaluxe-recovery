"""Tests for atomic idempotent ImportResult persistence."""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import HttpUrl, TypeAdapter
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from reinaluxe_recovery.importing import (
    ImportResult,
    ImportWarning,
    ImportWarningCode,
    ImportWarningSeverity,
)
from reinaluxe_recovery.persistence import (
    ImportPersistenceService,
    PersistDisposition,
    PersistenceConflictError,
    PersistenceContractError,
    PersistenceRepository,
    PersistImportResult,
    SessionFactory,
)
from reinaluxe_recovery.persistence.enums import StoredImportStatus
from reinaluxe_recovery.persistence.models import (
    ArticleVersionModel,
    CrawlRecordModel,
    ImportWarningModel,
    PageIdentityModel,
)


def _new_observation(
    original: ImportResult,
    *,
    fetched_at: datetime,
    source_hash: str | None = None,
    title: str | None = None,
) -> ImportResult:
    assert original.article is not None
    selected_hash = source_hash or original.source_hash
    snapshot_id = uuid4()
    snapshot = original.snapshot.model_copy(
        update={
            "id": snapshot_id,
            "captured_at": fetched_at,
            "content_hash": selected_hash,
            "raw_html": (
                original.snapshot.raw_html
                if source_hash is None
                else f"{original.snapshot.raw_html}\n<!-- changed -->"
            ),
        }
    )
    article = original.article.model_copy(
        update={
            "id": uuid4(),
            "source_snapshot_id": snapshot_id,
            "normalized_at": fetched_at,
            "source_content_hash": selected_hash,
            "title": title or original.article.title,
        }
    )
    return ImportResult.model_validate(
        original.model_dump()
        | {
            "snapshot": snapshot,
            "article": article,
            "source_hash": selected_hash,
        }
    )


def _with_warning(import_result: ImportResult) -> ImportResult:
    warning = ImportWarning(
        severity=ImportWarningSeverity.WARNING,
        code=ImportWarningCode.INVALID_DATE,
        message="An optional date was ignored.",
        location="datePublished",
    )
    return ImportResult.model_validate(
        import_result.model_dump() | {"warnings": [*import_result.warnings, warning]}
    )


def _counts(session_factory: SessionFactory) -> tuple[int, int, int, int]:
    with session_factory() as session:
        return (
            session.scalar(select(func.count(PageIdentityModel.id))) or 0,
            session.scalar(select(func.count(CrawlRecordModel.id))) or 0,
            session.scalar(select(func.count(ArticleVersionModel.id))) or 0,
            session.scalar(select(func.count(ImportWarningModel.id))) or 0,
        )


def test_first_success_creates_full_history_and_pointer(
    persistence_service: ImportPersistenceService,
    session_factory: SessionFactory,
    successful_import: ImportResult,
) -> None:
    """The first success creates its page, crawl, Article, warning, and head."""
    result = persistence_service.save_import_result(_with_warning(successful_import))

    assert result.page_disposition is PersistDisposition.CREATED
    assert result.crawl_disposition is PersistDisposition.CREATED
    assert result.article_disposition is PersistDisposition.CREATED
    assert result.article_version_number == 1
    assert result.article_version_id is not None
    assert result.warnings_persisted == 1
    with session_factory() as session:
        page = session.get(PageIdentityModel, result.page_id)
        assert page is not None
        assert page.current_article_version_id == result.article_version_id
    assert _counts(session_factory) == (1, 1, 1, 1)


def test_exact_repeat_is_fully_idempotent(
    persistence_service: ImportPersistenceService,
    session_factory: SessionFactory,
    successful_import: ImportResult,
) -> None:
    """An identical page/time/source tuple reuses every stored record."""
    import_result = _with_warning(successful_import)
    first = persistence_service.save_import_result(import_result)
    second = persistence_service.save_import_result(import_result)

    assert second.page_disposition is PersistDisposition.REUSED
    assert second.crawl_disposition is PersistDisposition.REUSED
    assert second.article_disposition is PersistDisposition.REUSED
    assert second.page_id == first.page_id
    assert second.crawl_id == first.crawl_id
    assert second.article_version_id == first.article_version_id
    assert _counts(session_factory) == (1, 1, 1, 1)


def test_new_crawl_with_unchanged_content_reuses_article(
    persistence_service: ImportPersistenceService,
    session_factory: SessionFactory,
    successful_import: ImportResult,
) -> None:
    """Transport-only changes create crawl history without a content version."""
    first = persistence_service.save_import_result(successful_import)
    later = _new_observation(
        successful_import,
        fetched_at=successful_import.snapshot.captured_at + timedelta(hours=1),
    )
    second = persistence_service.save_import_result(later)

    assert second.crawl_disposition is PersistDisposition.CREATED
    assert second.article_disposition is PersistDisposition.REUSED
    assert second.article_version_id == first.article_version_id
    assert second.article_version_number == 1
    assert _counts(session_factory)[:3] == (1, 2, 1)


def test_changed_imports_create_sequential_versions(
    persistence_service: ImportPersistenceService,
    session_factory: SessionFactory,
    successful_import: ImportResult,
) -> None:
    """Each distinct normalized payload advances history by exactly one."""
    first = persistence_service.save_import_result(successful_import)
    second_import = _new_observation(
        successful_import,
        fetched_at=successful_import.snapshot.captured_at + timedelta(hours=1),
        source_hash="b" * 64,
        title="Second editorial version",
    )
    second = persistence_service.save_import_result(second_import)
    third = persistence_service.save_import_result(
        _new_observation(
            second_import,
            fetched_at=successful_import.snapshot.captured_at + timedelta(hours=2),
            source_hash="c" * 64,
            title="Third editorial version",
        )
    )

    assert first.article_version_number == 1
    assert second.article_disposition is PersistDisposition.VERSION_CREATED
    assert second.article_version_number == 2
    assert third.article_disposition is PersistDisposition.VERSION_CREATED
    assert third.article_version_number == 3
    with session_factory() as session:
        page = session.get(PageIdentityModel, first.page_id)
        assert page is not None
        assert page.current_article_version_id == third.article_version_id
    assert _counts(session_factory)[:3] == (1, 3, 3)


def test_canonical_fragments_reuse_page_but_queries_remain_distinct(
    persistence_service: ImportPersistenceService,
    session_factory: SessionFactory,
    successful_import: ImportResult,
) -> None:
    """Conservative canonical normalization controls page identity."""
    assert successful_import.article is not None
    canonical = str(successful_import.article.canonical_url)
    first_article = successful_import.article.model_copy(
        update={
            "canonical_url": TypeAdapter(HttpUrl).validate_python(f"{canonical}#first")
        }
    )
    first_import = ImportResult.model_validate(
        successful_import.model_dump() | {"article": first_article}
    )
    persistence_service.save_import_result(first_import)

    changed = _new_observation(
        first_import,
        fetched_at=successful_import.snapshot.captured_at + timedelta(hours=1),
    )
    assert changed.article is not None
    changed_article = changed.article.model_copy(
        update={
            "canonical_url": TypeAdapter(HttpUrl).validate_python(f"{canonical}#second")
        }
    )
    persistence_service.save_import_result(
        ImportResult.model_validate(changed.model_dump() | {"article": changed_article})
    )

    with session_factory() as session:
        assert len(PersistenceRepository(session).list_pages()) == 1


def test_failed_import_persists_diagnostics_without_article(
    persistence_service: ImportPersistenceService,
    session_factory: SessionFactory,
    failed_import: ImportResult,
) -> None:
    """Controlled failures retain crawl evidence but never create a version."""
    result = persistence_service.save_import_result(failed_import)

    assert result.article_disposition is PersistDisposition.FAILED
    assert result.article_version_id is None
    assert result.failure_message
    with session_factory() as session:
        crawl = session.get(CrawlRecordModel, result.crawl_id)
        page = session.get(PageIdentityModel, result.page_id)
        assert crawl is not None
        assert crawl.import_status is StoredImportStatus.FAILED
        assert crawl.fatal_diagnostics
        assert page is not None
        assert page.current_article_version_id is None
    assert _counts(session_factory)[2] == 0


def test_observation_window_handles_out_of_order_history(
    persistence_service: ImportPersistenceService,
    session_factory: SessionFactory,
    successful_import: ImportResult,
) -> None:
    """Historical imports move first_seen backward but never reduce last_seen."""
    base_time = successful_import.snapshot.captured_at
    persistence_service.save_import_result(successful_import)
    persistence_service.save_import_result(
        _new_observation(successful_import, fetched_at=base_time + timedelta(days=2))
    )
    persistence_service.save_import_result(
        _new_observation(successful_import, fetched_at=base_time - timedelta(days=2))
    )

    with session_factory() as session:
        page = session.scalar(select(PageIdentityModel))
        assert page is not None
        assert page.first_seen_at == base_time - timedelta(days=2)
        assert page.last_seen_at == base_time + timedelta(days=2)


class _FailAfterCrawl(ImportPersistenceService):
    def _after_crawl_flush(self, session: Session) -> None:
        del session
        raise RuntimeError("injected failure before Article creation")


class _FailAfterArticle(ImportPersistenceService):
    def _after_article_flush(self, session: Session) -> None:
        del session
        raise RuntimeError("injected failure before pointer update")


class _ConstraintConflict(ImportPersistenceService):
    def _save(
        self,
        session: Session,
        import_result: ImportResult,
        canonical_url: str,
        content_hash: str | None,
    ) -> PersistImportResult:
        del session, import_result, canonical_url, content_hash
        raise IntegrityError("INSERT", {}, RuntimeError("unique constraint"))


@pytest.mark.parametrize("service_type", [_FailAfterCrawl, _FailAfterArticle])
def test_injected_failure_rolls_back_every_record(
    service_type: type[ImportPersistenceService],
    session_factory: SessionFactory,
    successful_import: ImportResult,
) -> None:
    """Failures on either side of Article flush leave no partial state."""
    service = service_type(session_factory)

    with pytest.raises(RuntimeError, match="injected failure"):
        service.save_import_result(_with_warning(successful_import))

    assert _counts(session_factory) == (0, 0, 0, 0)


def test_contract_mismatch_is_rejected_before_writing(
    persistence_service: ImportPersistenceService,
    session_factory: SessionFactory,
    successful_import: ImportResult,
) -> None:
    """Cross-record source hash mismatch cannot enter a transaction."""
    invalid = successful_import.model_copy(
        update={
            "snapshot": successful_import.snapshot.model_copy(
                update={"content_hash": "e" * 64}
            )
        }
    )

    with pytest.raises(PersistenceContractError, match="content_hash"):
        persistence_service.save_import_result(invalid)

    assert _counts(session_factory) == (0, 0, 0, 0)


def test_constraint_conflict_is_reported_explicitly(
    session_factory: SessionFactory,
    successful_import: ImportResult,
) -> None:
    """A final database uniqueness race is never swallowed or misreported."""
    service = _ConstraintConflict(session_factory)

    with pytest.raises(PersistenceConflictError, match="uniqueness constraint"):
        service.save_import_result(successful_import)

    assert _counts(session_factory) == (0, 0, 0, 0)
