"""Internal SQLAlchemy schema for local content-import history."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from reinaluxe_recovery.persistence.enums import (
    StoredImportStatus,
    StoredWarningSeverity,
)
from reinaluxe_recovery.persistence.exceptions import NaiveDatetimeError


def utc_now() -> datetime:
    """Return the current time as an aware UTC datetime."""
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator[datetime]):
    """Store aware datetimes as canonical UTC ISO 8601 strings in SQLite."""

    impl = String(40)
    cache_ok = True

    def process_bind_param(
        self,
        value: datetime | None,
        dialect: Dialect,
    ) -> str | None:
        """Reject naive values and serialize aware values in UTC."""
        del dialect
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise NaiveDatetimeError("database timestamps must be timezone-aware")
        return value.astimezone(UTC).isoformat()

    def process_result_value(
        self,
        value: str | None,
        dialect: Dialect,
    ) -> datetime | None:
        """Restore stored values as aware UTC datetimes."""
        del dialect
        if value is None:
            return None
        restored = datetime.fromisoformat(value)
        if restored.tzinfo is None or restored.utcoffset() is None:
            raise NaiveDatetimeError("stored database timestamp is timezone-naive")
        return restored.astimezone(UTC)


class Base(DeclarativeBase):
    """Declarative base kept internal to the persistence layer."""


class PageIdentityModel(Base):
    """Stable page identity and pointers to its local history."""

    __tablename__ = "page_identities"
    __table_args__ = (
        UniqueConstraint("canonical_url", name="uq_page_identities_canonical_url"),
        Index("ix_page_identities_normalized_url", "normalized_url"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_url: Mapped[str] = mapped_column(Text, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    current_article_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(
            "article_versions.id",
            name="fk_page_identities_current_article_version",
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
            use_alter=True,
        ),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utc_now, onupdate=utc_now
    )

    crawl_records: Mapped[list[CrawlRecordModel]] = relationship(
        back_populates="page",
        foreign_keys="CrawlRecordModel.page_id",
        cascade="save-update, merge",
        passive_deletes=True,
    )
    article_versions: Mapped[list[ArticleVersionModel]] = relationship(
        back_populates="page",
        foreign_keys="ArticleVersionModel.page_id",
        cascade="save-update, merge",
        passive_deletes=True,
    )
    current_article_version: Mapped[ArticleVersionModel | None] = relationship(
        foreign_keys=[current_article_version_id],
        post_update=True,
    )


class CrawlRecordModel(Base):
    """Raw import observation associated with one page identity."""

    __tablename__ = "crawl_records"
    __table_args__ = (
        UniqueConstraint(
            "page_id",
            "fetched_at",
            "source_html_hash",
            name="uq_crawl_records_idempotency",
        ),
        Index("ix_crawl_records_page_fetched", "page_id", "fetched_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    page_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "page_identities.id",
            name="fk_crawl_records_page",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    fetched_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_headers: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    source_html_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    import_status: Mapped[StoredImportStatus] = mapped_column(
        Enum(
            StoredImportStatus,
            values_callable=lambda enum: [item.value for item in enum],
            native_enum=False,
            create_constraint=True,
            name="stored_import_status",
        ),
        nullable=False,
    )
    fatal_diagnostics: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utc_now
    )

    page: Mapped[PageIdentityModel] = relationship(
        back_populates="crawl_records",
        foreign_keys=[page_id],
    )
    article_versions: Mapped[list[ArticleVersionModel]] = relationship(
        back_populates="source_crawl",
        cascade="save-update, merge",
        passive_deletes=True,
    )
    warnings: Mapped[list[ImportWarningModel]] = relationship(
        back_populates="crawl_record",
        cascade="save-update, merge",
        passive_deletes=True,
    )


class ArticleVersionModel(Base):
    """Immutable normalized Article payload for one content version."""

    __tablename__ = "article_versions"
    __table_args__ = (
        UniqueConstraint(
            "page_id",
            "version_number",
            name="uq_article_versions_page_version",
        ),
        UniqueConstraint(
            "page_id",
            "normalized_content_hash",
            name="uq_article_versions_page_content_hash",
        ),
        CheckConstraint("version_number > 0", name="ck_article_versions_positive"),
        Index("ix_article_versions_page_version", "page_id", "version_number"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    page_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "page_identities.id",
            name="fk_article_versions_page",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    crawl_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "crawl_records.id",
            name="fk_article_versions_crawl",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    normalized_article_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False
    )
    normalized_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    modified_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utc_now
    )

    page: Mapped[PageIdentityModel] = relationship(
        back_populates="article_versions",
        foreign_keys=[page_id],
    )
    source_crawl: Mapped[CrawlRecordModel] = relationship(
        back_populates="article_versions",
        foreign_keys=[crawl_id],
    )


class ImportWarningModel(Base):
    """One warning or fatal diagnostic linked to its crawl record."""

    __tablename__ = "import_warnings"
    __table_args__ = (Index("ix_import_warnings_crawl", "crawl_id"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    crawl_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "crawl_records.id",
            name="fk_import_warnings_crawl",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    warning_code: Mapped[str] = mapped_column(String(100), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[StoredWarningSeverity] = mapped_column(
        Enum(
            StoredWarningSeverity,
            values_callable=lambda enum: [item.value for item in enum],
            native_enum=False,
            create_constraint=True,
            name="stored_warning_severity",
        ),
        nullable=False,
    )
    field_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_location: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utc_now
    )

    crawl_record: Mapped[CrawlRecordModel] = relationship(
        back_populates="warnings",
        foreign_keys=[crawl_id],
    )
