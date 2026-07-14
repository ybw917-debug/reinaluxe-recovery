"""Shared temporary-database fixtures for persistence behavior tests."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from pydantic import HttpUrl, TypeAdapter

from reinaluxe_recovery.importing import HtmlFileInput, ImportResult, import_html_file
from reinaluxe_recovery.persistence import (
    ImportPersistenceService,
    SessionFactory,
    create_database_engine,
    create_session_factory,
    database_url_from_path,
)
from reinaluxe_recovery.persistence.models import Base

IMPORT_FIXTURES = Path(__file__).parents[1] / "importing" / "fixtures"
HTTP_URL = TypeAdapter(HttpUrl)


@pytest.fixture
def session_factory(tmp_path: Path) -> Iterator[SessionFactory]:
    """Provide an isolated SQLite schema and dispose it after each test."""
    engine = create_database_engine(database_url_from_path(tmp_path / "stage004b.db"))
    Base.metadata.create_all(engine)
    yield create_session_factory(engine)
    engine.dispose()


@pytest.fixture
def persistence_service(
    session_factory: SessionFactory,
) -> ImportPersistenceService:
    """Provide the production service over the isolated session factory."""
    return ImportPersistenceService(session_factory)


@pytest.fixture
def successful_import() -> ImportResult:
    """Return one representative successful offline ImportResult."""
    from datetime import UTC, datetime

    return import_html_file(
        HtmlFileInput(
            html_path=IMPORT_FIXTURES / "complete-article.html",
            source_url=HTTP_URL.validate_python(
                "https://owner.example/articles/offline/"
            ),
            fetched_at=datetime(2026, 7, 14, 12, 0, tzinfo=UTC),
        )
    )


@pytest.fixture
def failed_import() -> ImportResult:
    """Return one representative failed offline ImportResult."""
    from datetime import UTC, datetime

    return import_html_file(
        HtmlFileInput(
            html_path=IMPORT_FIXTURES / "no-article-body.html",
            source_url=HTTP_URL.validate_python(
                "https://owner.example/articles/failed/"
            ),
            fetched_at=datetime(2026, 7, 14, 12, 0, tzinfo=UTC),
        )
    )
