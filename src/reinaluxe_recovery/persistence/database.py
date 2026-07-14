"""Synchronous SQLite engine and transaction configuration."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session, sessionmaker

from reinaluxe_recovery.persistence.exceptions import DatabaseConfigurationError
from reinaluxe_recovery.persistence.models import Base

DEFAULT_DATABASE_PATH = Path("data") / "reinaluxe-recovery.db"


def database_url_from_path(path: Path) -> str:
    """Build a SQLite URL for a local filesystem path."""
    absolute_path = path.expanduser().resolve()
    return URL.create(
        drivername="sqlite+pysqlite",
        database=str(absolute_path),
    ).render_as_string()


DEFAULT_DATABASE_URL = database_url_from_path(DEFAULT_DATABASE_PATH)


def _enable_sqlite_foreign_keys(
    dbapi_connection: Any,
    connection_record: Any,
) -> None:
    """Enable SQLite foreign-key enforcement for every pooled connection."""
    del connection_record
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def create_database_engine(
    database_url: str = DEFAULT_DATABASE_URL,
    *,
    echo: bool = False,
) -> Engine:
    """Create a synchronous SQLite engine without connecting immediately."""
    parsed_url = make_url(database_url)
    if parsed_url.get_backend_name() != "sqlite":
        raise DatabaseConfigurationError("only local SQLite URLs are supported")
    engine = create_engine(
        parsed_url,
        echo=echo,
        future=True,
        connect_args={"check_same_thread": False},
    )
    event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    return engine


SessionFactory = sessionmaker[Session]


def create_session_factory(engine: Engine) -> SessionFactory:
    """Create an explicit synchronous session factory."""
    return sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


@contextmanager
def transactional_session(factory: SessionFactory) -> Iterator[Session]:
    """Commit one unit of work or roll it back on any exception."""
    with factory() as session:
        with session.begin():
            yield session


persistence_metadata = Base.metadata
