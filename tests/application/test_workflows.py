"""Tests for thin application orchestration boundaries."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import BaseModel, HttpUrl, TypeAdapter

from reinaluxe_recovery.application import (
    ImportWorkflowResult,
    OfflineImportWorkflow,
    PageDetails,
    PageInventoryResult,
    PageQueryService,
)
from reinaluxe_recovery.importing import (
    HtmlFileInput,
    ImportResult,
    import_html_file,
)
from reinaluxe_recovery.persistence import (
    create_database_engine,
    create_session_factory,
    initialize_database,
)

FIXTURES = Path(__file__).parents[1] / "importing" / "fixtures"


def _input(name: str = "minimal-article.html") -> HtmlFileInput:
    return HtmlFileInput(
        html_path=FIXTURES / name,
        source_url=TypeAdapter(HttpUrl).validate_python(
            "https://owner.example/application/"
        ),
        fetched_at=datetime(2026, 7, 14, 12, 0, tzinfo=UTC),
    )


def test_import_workflow_parses_once_and_returns_pydantic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Orchestration delegates one import and returns detached contracts."""
    lifecycle = initialize_database(tmp_path / "workflow.db")
    engine = create_database_engine(lifecycle.database_url)
    factory = create_session_factory(engine)
    calls = 0
    real_import = import_html_file

    def counted(import_input: HtmlFileInput) -> ImportResult:
        nonlocal calls
        calls += 1
        return real_import(import_input)

    monkeypatch.setattr(
        "reinaluxe_recovery.application.import_workflow.import_html_file",
        counted,
    )
    try:
        result = OfflineImportWorkflow(factory).run(_input())
    finally:
        engine.dispose()

    assert calls == 1
    assert isinstance(result, ImportWorkflowResult)
    assert isinstance(result, BaseModel)
    assert result.persistence_result is not None


def test_page_query_orchestration_returns_only_pydantic_dtos(
    tmp_path: Path,
) -> None:
    """Inventory and detail application results never expose ORM instances."""
    lifecycle = initialize_database(tmp_path / "queries.db")
    engine = create_database_engine(lifecycle.database_url)
    factory = create_session_factory(engine)
    try:
        OfflineImportWorkflow(factory).run(_input())
        query_service = PageQueryService(factory)
        inventory = query_service.list_pages()
        details = query_service.show_page(
            "https://owner.example/application/",
            include_history=True,
        )
    finally:
        engine.dispose()

    assert isinstance(inventory, PageInventoryResult)
    assert isinstance(details, PageDetails)
    assert len(inventory.items) == 1
    assert inventory.items[0].crawl_count == 1
    assert inventory.items[0].article_version_count == 1
    assert details.latest_article is not None
    assert len(details.crawl_history) == 1
    assert len(details.article_version_history) == 1
