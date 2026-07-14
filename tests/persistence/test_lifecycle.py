"""Tests for safe programmatic local-database lifecycle orchestration."""

from pathlib import Path

import pytest

from reinaluxe_recovery.persistence import (
    DatabaseConfigurationError,
    DatabaseLifecycleError,
    PersistenceRepository,
    build_sqlite_url,
    create_database_engine,
    create_session_factory,
    database_is_current,
    get_database_revision,
    initialize_database,
    resolve_database_path,
    upgrade_database,
)
from reinaluxe_recovery.persistence.lifecycle import PROJECT_ROOT


def test_default_database_path_resolves_inside_ignored_data_directory() -> None:
    """The owner-facing default is stable regardless of the current directory."""
    assert (
        resolve_database_path()
        == (PROJECT_ROOT / "data" / "reinaluxe-recovery.db").resolve()
    )


def test_custom_relative_database_path_uses_current_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A supplied relative path is understandable from the caller's location."""
    monkeypatch.chdir(tmp_path)
    assert (
        resolve_database_path(Path("local") / "custom.db")
        == (tmp_path / "local" / "custom.db").resolve()
    )


def test_initialize_creates_parent_and_current_database(tmp_path: Path) -> None:
    """Explicit initialization creates parents, migrates, and checks health."""
    database_path = tmp_path / "nested" / "owner.db"

    result = initialize_database(database_path)

    assert database_path.exists()
    assert result.database_path == database_path.resolve()
    assert result.previous_revision is None
    assert result.current_revision == result.target_revision
    assert result.migration_performed
    assert result.healthy
    assert get_database_revision(database_path) == result.target_revision
    assert database_is_current(database_path)
    engine = create_database_engine(result.database_url)
    try:
        with create_session_factory(engine)() as session:
            assert PersistenceRepository(session).database_health_check()
    finally:
        engine.dispose()


def test_repeated_initialization_is_idempotent(tmp_path: Path) -> None:
    """A current database is retained and reports no migration work."""
    database_path = tmp_path / "repeat.db"
    first = initialize_database(database_path)
    second = initialize_database(database_path)

    assert second.previous_revision == first.current_revision
    assert second.current_revision == first.current_revision
    assert not second.migration_performed
    assert second.healthy


def test_upgrade_existing_empty_file_to_current_revision(tmp_path: Path) -> None:
    """Upgrade can migrate an existing file without deleting or replacing it."""
    database_path = tmp_path / "existing.db"
    database_path.touch()

    result = upgrade_database(database_path)

    assert result.previous_revision is None
    assert result.current_revision == result.target_revision
    assert database_path.exists()


def test_upgrade_requires_existing_database(tmp_path: Path) -> None:
    """Only initialize_database is allowed to create a missing database."""
    with pytest.raises(DatabaseLifecycleError, match="does not exist"):
        upgrade_database(tmp_path / "missing.db")


def test_invalid_database_paths_are_rejected(tmp_path: Path) -> None:
    """Directories and impossible parent paths fail without stack traces."""
    with pytest.raises(DatabaseLifecycleError, match="not a file"):
        resolve_database_path(tmp_path)

    parent_file = tmp_path / "parent-file"
    parent_file.write_text("not a directory", encoding="utf-8")
    with pytest.raises(DatabaseLifecycleError, match="could not create"):
        initialize_database(parent_file / "database.db")


def test_non_sqlite_urls_are_rejected() -> None:
    """Lifecycle configuration cannot connect to a server database."""
    with pytest.raises(DatabaseConfigurationError, match="SQLite"):
        build_sqlite_url("postgresql://localhost/reinaluxe")
