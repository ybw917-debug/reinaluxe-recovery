"""Tests for the synchronous SQLite database foundation."""

from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import StatementError

from reinaluxe_recovery.persistence import (
    DatabaseConfigurationError,
    create_database_engine,
    create_session_factory,
    database_url_from_path,
    transactional_session,
)
from reinaluxe_recovery.persistence.models import Base, PageIdentityModel


def test_engine_creation_uses_temporary_sqlite_file(tmp_path: Path) -> None:
    """The engine connects only to the explicitly supplied temporary path."""
    database_path = tmp_path / "engine.db"
    engine = create_database_engine(database_url_from_path(database_path))

    with engine.connect() as connection:
        assert connection.scalar(text("SELECT 1")) == 1

    assert database_path.exists()
    assert database_path.resolve().is_relative_to(tmp_path.resolve())


def test_sqlite_foreign_keys_are_enabled(tmp_path: Path) -> None:
    """Every engine connection enables SQLite foreign-key enforcement."""
    engine = create_database_engine(database_url_from_path(tmp_path / "foreign.db"))

    with engine.connect() as connection:
        assert connection.scalar(text("PRAGMA foreign_keys")) == 1


def test_metadata_creates_all_required_tables(tmp_path: Path) -> None:
    """The production metadata contains the four Stage 004A tables."""
    engine = create_database_engine(database_url_from_path(tmp_path / "metadata.db"))
    Base.metadata.create_all(engine)

    assert set(inspect(engine).get_table_names()) == {
        "article_versions",
        "crawl_records",
        "import_warnings",
        "page_identities",
    }


def test_aware_datetimes_are_normalized_to_utc(tmp_path: Path) -> None:
    """Aware offsets round-trip through SQLite as explicit UTC values."""
    engine = create_database_engine(database_url_from_path(tmp_path / "aware.db"))
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    supplied = datetime(
        2026,
        7,
        14,
        12,
        0,
        tzinfo=timezone(timedelta(hours=8)),
    )
    page_id = uuid4()

    with transactional_session(factory) as session:
        session.add(
            PageIdentityModel(
                id=page_id,
                canonical_url="https://owner.example/article/",
                normalized_url="https://owner.example/article/",
                first_seen_at=supplied,
                last_seen_at=supplied,
            )
        )

    with factory() as session:
        stored = session.get(PageIdentityModel, page_id)
        assert stored is not None
        assert stored.first_seen_at.tzinfo is UTC
        assert stored.first_seen_at == supplied.astimezone(UTC)


def test_naive_datetimes_are_rejected(tmp_path: Path) -> None:
    """The persistence boundary never silently assumes a timezone."""
    engine = create_database_engine(database_url_from_path(tmp_path / "naive.db"))
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)

    with pytest.raises(StatementError, match="timezone-aware"):
        with transactional_session(factory) as session:
            session.add(
                PageIdentityModel(
                    canonical_url="https://owner.example/naive/",
                    normalized_url="https://owner.example/naive/",
                    first_seen_at=datetime(2026, 7, 14, 12, 0),
                    last_seen_at=datetime(2026, 7, 14, 12, 0),
                )
            )


def test_non_sqlite_database_url_is_rejected() -> None:
    """Stage 004A cannot accidentally connect to a cloud database."""
    with pytest.raises(DatabaseConfigurationError, match="SQLite"):
        create_database_engine("postgresql://localhost/reinaluxe")
