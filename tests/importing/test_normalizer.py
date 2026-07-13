"""Tests for domain normalization and controlled fatal outcomes."""

from datetime import UTC, datetime
from pathlib import Path

from reinaluxe_recovery.domain import ArticleStatus, ContentType, SearchIntent
from reinaluxe_recovery.importing import (
    HtmlFileInput,
    ImportStatus,
    ImportWarningCode,
    ImportWarningSeverity,
    import_html_file,
)

FIXTURES = Path(__file__).parent / "fixtures"
FETCHED_AT = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)
SOURCE_URL = "https://owner.example/articles/offline/"


def _import(name: str):  # type: ignore[no-untyped-def]
    return import_html_file(
        HtmlFileInput(
            html_path=FIXTURES / name,
            source_url=SOURCE_URL,
            fetched_at=FETCHED_AT,
        )
    )


def test_valid_complete_html_import() -> None:
    """Complete HTML becomes linked CrawlSnapshot and Article records."""
    result = _import("complete-article.html")

    assert result.status is ImportStatus.SUCCEEDED
    assert result.article is not None
    assert result.article.source_snapshot_id == result.snapshot.id
    assert result.article.source_content_hash == result.source_hash
    assert result.article.status is ArticleStatus.UNKNOWN
    assert result.article.content_type is ContentType.OTHER
    assert result.article.search_intents == [SearchIntent.UNKNOWN]


def test_minimal_html_import_keeps_optional_metadata_absent() -> None:
    """Missing canonical, dates, and description are not invented."""
    result = _import("minimal-article.html")

    assert result.article is not None
    assert result.article.canonical_url is None
    assert result.article.published_at is None
    assert result.article.modified_at is None
    assert result.article.meta_description is None


def test_no_valid_article_body_is_controlled_fatal_result() -> None:
    """A structurally empty page returns a snapshot, warnings, and no Article."""
    result = _import("no-article-body.html")

    assert result.status is ImportStatus.FAILED
    assert result.article is None
    assert result.snapshot.raw_html is not None
    assert any(
        warning.code is ImportWarningCode.MISSING_ARTICLE_BODY
        and warning.severity is ImportWarningSeverity.FATAL
        for warning in result.warnings
    )
