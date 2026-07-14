"""Tests for the reviewed initial Alembic migration."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from reinaluxe_recovery.persistence import database_url_from_path

PROJECT_ROOT = Path(__file__).parents[2]
REQUIRED_TABLES = {
    "article_versions",
    "crawl_records",
    "import_warnings",
    "page_identities",
}


def _config(database_path: Path) -> Config:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    config.set_main_option(
        "sqlalchemy.url",
        database_url_from_path(database_path).replace("%", "%%"),
    )
    return config


def test_initial_migration_upgrades_empty_database(tmp_path: Path) -> None:
    """Upgrade creates all required tables in a temporary SQLite database."""
    database_path = tmp_path / "upgrade.db"
    command.upgrade(_config(database_path), "head")

    tables = set(
        inspect(create_engine(database_url_from_path(database_path))).get_table_names()
    )

    assert REQUIRED_TABLES <= tables
    assert "alembic_version" in tables
    assert database_path.resolve().is_relative_to(tmp_path.resolve())
    command.check(_config(database_path))


def test_initial_migration_downgrades_schema(tmp_path: Path) -> None:
    """Downgrade removes every Stage 004A persistence table."""
    database_path = tmp_path / "downgrade.db"
    config = _config(database_path)
    command.upgrade(config, "head")
    command.downgrade(config, "base")

    tables = set(
        inspect(create_engine(database_url_from_path(database_path))).get_table_names()
    )

    assert REQUIRED_TABLES.isdisjoint(tables)
