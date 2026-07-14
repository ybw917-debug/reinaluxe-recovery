"""Schema and relationship tests for internal ORM models."""

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import inspect

from reinaluxe_recovery.persistence import (
    create_database_engine,
    create_session_factory,
    database_url_from_path,
    transactional_session,
)
from reinaluxe_recovery.persistence.enums import (
    StoredImportStatus,
    StoredWarningSeverity,
)
from reinaluxe_recovery.persistence.models import (
    ArticleVersionModel,
    Base,
    CrawlRecordModel,
    ImportWarningModel,
    PageIdentityModel,
)

NOW = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)
HASH_A = "a" * 64
HASH_B = "b" * 64


def _engine(tmp_path: Path):  # type: ignore[no-untyped-def]
    engine = create_database_engine(database_url_from_path(tmp_path / "models.db"))
    Base.metadata.create_all(engine)
    return engine


def test_required_unique_constraints_and_indexes_exist(tmp_path: Path) -> None:
    """Introspection confirms the reviewed idempotency and history keys."""
    inspector = inspect(_engine(tmp_path))

    page_uniques = {
        item["name"] for item in inspector.get_unique_constraints("page_identities")
    }
    crawl_uniques = {
        item["name"] for item in inspector.get_unique_constraints("crawl_records")
    }
    article_uniques = {
        item["name"] for item in inspector.get_unique_constraints("article_versions")
    }
    assert "uq_page_identities_canonical_url" in page_uniques
    assert "uq_crawl_records_idempotency" in crawl_uniques
    assert {
        "uq_article_versions_page_version",
        "uq_article_versions_page_content_hash",
    } <= article_uniques

    assert "ix_page_identities_normalized_url" in {
        item["name"] for item in inspector.get_indexes("page_identities")
    }
    assert "ix_crawl_records_page_fetched" in {
        item["name"] for item in inspector.get_indexes("crawl_records")
    }
    assert "ix_article_versions_page_version" in {
        item["name"] for item in inspector.get_indexes("article_versions")
    }
    assert "ix_import_warnings_crawl" in {
        item["name"] for item in inspector.get_indexes("import_warnings")
    }


def test_basic_relationships_can_be_persisted(tmp_path: Path) -> None:
    """ORM relationships link history without exposing domain/Pydantic types."""
    engine = _engine(tmp_path)
    factory = create_session_factory(engine)
    page = PageIdentityModel(
        canonical_url="https://owner.example/article/",
        normalized_url="https://owner.example/article/",
        first_seen_at=NOW,
        last_seen_at=NOW,
    )
    crawl = CrawlRecordModel(
        page=page,
        fetched_at=NOW,
        status_code=200,
        response_headers={"content-type": "text/html"},
        source_html_hash=HASH_A,
        raw_html="<html lang='en'></html>",
        import_status=StoredImportStatus.SUCCEEDED,
        fatal_diagnostics=[],
    )
    article = ArticleVersionModel(
        page=page,
        source_crawl=crawl,
        normalized_article_json={"contract_version": "1.0"},
        normalized_content_hash=HASH_B,
        version_number=1,
    )
    warning = ImportWarningModel(
        crawl_record=crawl,
        warning_code="invalid_date",
        message="An optional date was ignored.",
        severity=StoredWarningSeverity.WARNING,
        source_location="datePublished",
    )
    page.current_article_version = article

    with transactional_session(factory) as session:
        session.add_all([page, crawl, article, warning])

    with factory() as session:
        stored_page = session.get(PageIdentityModel, page.id)
        assert stored_page is not None
        assert stored_page.current_article_version_id == article.id
        assert stored_page.crawl_records[0].id == crawl.id
        assert stored_page.article_versions[0].id == article.id
        assert stored_page.crawl_records[0].warnings[0].id == warning.id


def test_foreign_keys_use_conservative_delete_behavior(tmp_path: Path) -> None:
    """Historical records use RESTRICT rather than delete cascades."""
    inspector = inspect(_engine(tmp_path))
    tables = ("page_identities", "crawl_records", "article_versions", "import_warnings")

    foreign_keys = [
        foreign_key
        for table in tables
        for foreign_key in inspector.get_foreign_keys(table)
    ]

    assert foreign_keys
    assert all(item["options"].get("ondelete") == "RESTRICT" for item in foreign_keys)
