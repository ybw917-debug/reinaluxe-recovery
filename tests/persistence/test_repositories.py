"""Tests for detached read repositories over caller-owned sessions."""

from datetime import timedelta
from uuid import uuid4

from pydantic import BaseModel

from reinaluxe_recovery.importing import (
    ImportResult,
    ImportWarning,
    ImportWarningCode,
    ImportWarningSeverity,
)
from reinaluxe_recovery.persistence import (
    ImportPersistenceService,
    PersistenceRepository,
    PersistImportResult,
    SessionFactory,
    StoredArticleVersionSummary,
    StoredCrawlSummary,
    StoredImportWarningSummary,
    StoredPageSummary,
)
from reinaluxe_recovery.persistence.models import (
    ArticleVersionModel,
    CrawlRecordModel,
    ImportWarningModel,
    PageIdentityModel,
)


def _changed_import(original: ImportResult) -> ImportResult:
    assert original.article is not None
    source_hash = "d" * 64
    snapshot_id = uuid4()
    fetched_at = original.snapshot.captured_at + timedelta(hours=1)
    snapshot = original.snapshot.model_copy(
        update={
            "id": snapshot_id,
            "captured_at": fetched_at,
            "content_hash": source_hash,
            "raw_html": f"{original.snapshot.raw_html}\n<!-- revision -->",
        }
    )
    article = original.article.model_copy(
        update={
            "id": uuid4(),
            "source_snapshot_id": snapshot_id,
            "normalized_at": fetched_at,
            "source_content_hash": source_hash,
            "title": "Repository history revision",
        }
    )
    warning = ImportWarning(
        severity=ImportWarningSeverity.WARNING,
        code=ImportWarningCode.INVALID_DATE,
        message="An optional date was ignored.",
        location="dateModified",
    )
    return ImportResult.model_validate(
        original.model_dump()
        | {
            "snapshot": snapshot,
            "article": article,
            "source_hash": source_hash,
            "warnings": [warning],
        }
    )


def test_complete_repository_inventory_and_history(
    persistence_service: ImportPersistenceService,
    session_factory: SessionFactory,
    successful_import: ImportResult,
) -> None:
    """All required reads return ordered detached Pydantic summaries."""
    first = persistence_service.save_import_result(successful_import)
    second = persistence_service.save_import_result(_changed_import(successful_import))

    with session_factory() as session:
        repository = PersistenceRepository(session)
        pages = repository.list_pages()
        by_url = repository.get_page_by_url(first.canonical_url)
        by_id = repository.get_page_by_id(first.page_id)
        crawls = repository.list_crawl_records(first.canonical_url)
        crawl = repository.get_crawl_record(first.crawl_id)
        latest = repository.get_latest_article(first.canonical_url)
        versions = repository.list_article_versions(first.canonical_url)
        version = repository.get_article_version(first.article_version_id)  # type: ignore[arg-type]
        warnings = repository.list_import_warnings(second.crawl_id)

        assert repository.database_health_check()
        assert pages == [by_url] == [by_id]
        assert [item.id for item in crawls] == [second.crawl_id, first.crawl_id]
        assert crawl is not None and crawl.id == first.crawl_id
        assert latest is not None and latest.id == second.article_version_id
        assert [item.version_number for item in versions] == [1, 2]
        assert version is not None and version.version_number == 1
        assert len(warnings) == 1
        assert warnings[0].code == ImportWarningCode.INVALID_DATE.value

        public_values = [*pages, *crawls, *versions, *warnings]
        assert all(isinstance(item, BaseModel) for item in public_values)
        assert not any(
            isinstance(
                item,
                (
                    PageIdentityModel,
                    CrawlRecordModel,
                    ArticleVersionModel,
                    ImportWarningModel,
                ),
            )
            for item in public_values
        )


def test_persistence_dtos_round_trip_through_json(
    persistence_service: ImportPersistenceService,
    session_factory: SessionFactory,
    successful_import: ImportResult,
) -> None:
    """Service and repository DTOs preserve their validated JSON contracts."""
    outcome = persistence_service.save_import_result(_changed_import(successful_import))

    with session_factory() as session:
        repository = PersistenceRepository(session)
        page = repository.get_page_by_id(outcome.page_id)
        crawl = repository.get_crawl_record(outcome.crawl_id)
        article = repository.get_article_version(outcome.article_version_id)  # type: ignore[arg-type]
        warning = repository.list_import_warnings(outcome.crawl_id)[0]

    assert PersistImportResult.model_validate_json(outcome.model_dump_json()) == outcome
    assert page is not None
    assert StoredPageSummary.model_validate_json(page.model_dump_json()) == page
    assert crawl is not None
    assert StoredCrawlSummary.model_validate_json(crawl.model_dump_json()) == crawl
    assert article is not None
    assert (
        StoredArticleVersionSummary.model_validate_json(article.model_dump_json())
        == article
    )
    assert (
        StoredImportWarningSummary.model_validate_json(warning.model_dump_json())
        == warning
    )


def test_unknown_records_return_empty_results(
    session_factory: SessionFactory,
) -> None:
    """Absence is explicit and does not leak SQLAlchemy exceptions or models."""
    unknown = uuid4()
    with session_factory() as session:
        repository = PersistenceRepository(session)
        assert repository.get_page_by_id(unknown) is None
        assert repository.get_crawl_record(unknown) is None
        assert repository.get_article_version(unknown) is None
        assert repository.get_page_by_url("https://example.com/missing") is None
        assert repository.list_crawl_records("https://example.com/missing") == []
        assert repository.get_latest_article("https://example.com/missing") is None
        assert repository.list_article_versions("https://example.com/missing") == []
        assert repository.list_import_warnings(unknown) == []
