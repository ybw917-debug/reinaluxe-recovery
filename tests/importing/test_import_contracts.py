"""Tests for validated offline import boundary contracts."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from reinaluxe_recovery.importing import (
    HtmlFileInput,
    ImportResult,
    JsonFixtureInput,
    import_html_file,
    import_json_fixture,
    load_json_fixture,
)

FIXTURES = Path(__file__).parent / "fixtures"
FETCHED_AT = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)
SOURCE_URL = "https://owner.example/articles/offline/"


def test_html_file_input_requires_valid_url() -> None:
    """Standalone HTML provenance rejects an invalid source URL."""
    with pytest.raises(ValidationError):
        HtmlFileInput(
            html_path=FIXTURES / "minimal-article.html",
            source_url="not-a-url",
            fetched_at=FETCHED_AT,
        )


def test_html_file_input_rejects_naive_datetime() -> None:
    """Standalone HTML provenance requires an explicit timezone."""
    with pytest.raises(ValidationError):
        HtmlFileInput(
            html_path=FIXTURES / "minimal-article.html",
            source_url=SOURCE_URL,
            fetched_at=datetime(2026, 7, 14, 12, 0),
        )


def test_json_fixture_contract_and_import() -> None:
    """A structured local fixture validates and creates both domain records."""
    fixture = load_json_fixture(FIXTURES / "complete-fixture.json")
    result = import_json_fixture(fixture)

    assert isinstance(fixture, JsonFixtureInput)
    assert result.article is not None
    assert result.snapshot.http_status == 200
    assert result.snapshot.response_content_type == "text/html; charset=utf-8"


def test_source_hash_and_ids_are_stable() -> None:
    """Repeated imports of identical source produce stable hashes and IDs."""
    import_input = HtmlFileInput(
        html_path=FIXTURES / "complete-article.html",
        source_url=SOURCE_URL,
        fetched_at=FETCHED_AT,
    )
    first = import_html_file(import_input)
    second = import_html_file(import_input)

    assert first.source_hash == second.source_hash
    assert first.snapshot.id == second.snapshot.id
    assert first.article is not None
    assert second.article is not None
    assert first.article.id == second.article.id


def test_identical_html_at_different_urls_has_distinct_record_ids() -> None:
    """Provenance scopes deterministic IDs when page markup is identical."""
    first = import_html_file(
        HtmlFileInput(
            html_path=FIXTURES / "minimal-article.html",
            source_url="https://owner.example/first/",
            fetched_at=FETCHED_AT,
        )
    )
    second = import_html_file(
        HtmlFileInput(
            html_path=FIXTURES / "minimal-article.html",
            source_url="https://owner.example/second/",
            fetched_at=FETCHED_AT,
        )
    )

    assert first.source_hash == second.source_hash
    assert first.snapshot.id != second.snapshot.id
    assert first.article is not None
    assert second.article is not None
    assert first.article.id != second.article.id


def test_import_result_serialization_round_trip() -> None:
    """The full import envelope survives JSON serialization."""
    result = import_html_file(
        HtmlFileInput(
            html_path=FIXTURES / "complete-article.html",
            source_url=SOURCE_URL,
            fetched_at=FETCHED_AT,
        )
    )

    restored = ImportResult.model_validate_json(result.model_dump_json())

    assert restored == result
