"""Programmatic Alembic lifecycle for local SQLite database files."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from reinaluxe_recovery.persistence.database import (
    DEFAULT_DATABASE_PATH,
    create_database_engine,
    create_session_factory,
    database_url_from_path,
)
from reinaluxe_recovery.persistence.dto import DatabaseLifecycleResult
from reinaluxe_recovery.persistence.exceptions import (
    DatabaseConfigurationError,
    DatabaseLifecycleError,
)
from reinaluxe_recovery.persistence.repositories import PersistenceRepository

PROJECT_ROOT = Path(__file__).parents[3]
ALEMBIC_CONFIG_PATH = PROJECT_ROOT / "alembic.ini"
MIGRATIONS_PATH = PROJECT_ROOT / "migrations"


def resolve_database_path(database_path: Path | str | None = None) -> Path:
    """Resolve a user path, or the repository-local ignored default path."""
    selected = DEFAULT_DATABASE_PATH if database_path is None else Path(database_path)
    resolved = (
        (
            PROJECT_ROOT / selected
            if not selected.is_absolute() and database_path is None
            else selected
        )
        .expanduser()
        .resolve()
    )
    if resolved.exists() and not resolved.is_file():
        raise DatabaseLifecycleError(f"database path is not a file: {resolved}")
    return resolved


def build_sqlite_url(database: Path | str) -> str:
    """Build or validate a file-backed SQLite URL."""
    if isinstance(database, str) and "://" in database:
        try:
            parsed = make_url(database)
        except ValueError as error:
            raise DatabaseConfigurationError("invalid database URL") from error
        if parsed.get_backend_name() != "sqlite":
            raise DatabaseConfigurationError("only local SQLite URLs are supported")
        if not parsed.database or parsed.database == ":memory:":
            raise DatabaseConfigurationError("a file-backed SQLite URL is required")
        return parsed.render_as_string(hide_password=True)
    return database_url_from_path(resolve_database_path(database))


def _alembic_config(database_url: str) -> Config:
    config = Config(str(ALEMBIC_CONFIG_PATH))
    config.attributes["configure_logger"] = False
    config.set_main_option("script_location", str(MIGRATIONS_PATH))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config


def _target_revision(database_url: str) -> str:
    revision = ScriptDirectory.from_config(
        _alembic_config(database_url)
    ).get_current_head()
    if revision is None:
        raise DatabaseLifecycleError("no Alembic head revision is configured")
    return revision


def get_database_revision(database_path: Path | str | None = None) -> str | None:
    """Read the applied Alembic revision without changing the database."""
    resolved = resolve_database_path(database_path)
    if not resolved.exists():
        return None
    engine = create_database_engine(build_sqlite_url(resolved))
    try:
        with engine.connect() as connection:
            return MigrationContext.configure(connection).get_current_revision()
    except Exception as error:
        raise DatabaseLifecycleError(
            f"could not read database revision for {resolved}: {error}"
        ) from error
    finally:
        engine.dispose()


def database_is_current(database_path: Path | str | None = None) -> bool:
    """Return whether an existing database is at the single Alembic head."""
    resolved = resolve_database_path(database_path)
    database_url = build_sqlite_url(resolved)
    return get_database_revision(resolved) == _target_revision(database_url)


def upgrade_database(
    database_path: Path | str | None = None,
) -> DatabaseLifecycleResult:
    """Upgrade an existing database without creating its parent directory."""
    resolved = resolve_database_path(database_path)
    if not resolved.exists():
        raise DatabaseLifecycleError(f"database does not exist: {resolved}")
    return _upgrade(resolved)


def initialize_database(
    database_path: Path | str | None = None,
) -> DatabaseLifecycleResult:
    """Create parent directories and safely migrate a local database to head."""
    resolved = resolve_database_path(database_path)
    try:
        resolved.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise DatabaseLifecycleError(
            f"could not create database directory {resolved.parent}: {error}"
        ) from error
    return _upgrade(resolved)


def _upgrade(database_path: Path) -> DatabaseLifecycleResult:
    database_url = build_sqlite_url(database_path)
    target_revision = _target_revision(database_url)
    previous_revision = get_database_revision(database_path)
    try:
        if previous_revision != target_revision:
            command.upgrade(_alembic_config(database_url), "head")
        current_revision = get_database_revision(database_path)
        if current_revision != target_revision:
            raise DatabaseLifecycleError(
                "database migration completed without reaching the target revision"
            )
        engine = create_database_engine(database_url)
        try:
            with create_session_factory(engine)() as session:
                healthy = PersistenceRepository(session).database_health_check()
        finally:
            engine.dispose()
    except DatabaseLifecycleError:
        raise
    except Exception as error:
        raise DatabaseLifecycleError(
            f"could not initialize or upgrade {database_path}: {error}"
        ) from error
    if not healthy:
        raise DatabaseLifecycleError(f"database health check failed: {database_path}")
    return DatabaseLifecycleResult(
        database_path=database_path,
        database_url=make_url(database_url).render_as_string(hide_password=True),
        previous_revision=previous_revision,
        current_revision=current_revision,
        target_revision=target_revision,
        migration_performed=previous_revision != current_revision,
        healthy=healthy,
    )
