"""Create the initial local persistence schema.

Revision ID: 20260714_0001
Revises: None
Create Date: 2026-07-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260714_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create page, crawl, article-version, and warning history tables."""
    op.create_table(
        "page_identities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("normalized_url", sa.Text(), nullable=False),
        sa.Column("first_seen_at", sa.String(length=40), nullable=False),
        sa.Column("last_seen_at", sa.String(length=40), nullable=False),
        sa.Column("current_article_version_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("canonical_url", name="uq_page_identities_canonical_url"),
    )
    op.create_index(
        "ix_page_identities_normalized_url",
        "page_identities",
        ["normalized_url"],
        unique=False,
    )

    op.create_table(
        "crawl_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("page_id", sa.Uuid(), nullable=False),
        sa.Column("fetched_at", sa.String(length=40), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("response_headers", sa.JSON(), nullable=False),
        sa.Column("source_html_hash", sa.String(length=64), nullable=False),
        sa.Column("raw_html", sa.Text(), nullable=True),
        sa.Column(
            "import_status",
            sa.Enum(
                "succeeded",
                "failed",
                name="stored_import_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("fatal_diagnostics", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(
            ["page_id"],
            ["page_identities.id"],
            name="fk_crawl_records_page",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "page_id",
            "fetched_at",
            "source_html_hash",
            name="uq_crawl_records_idempotency",
        ),
    )
    op.create_index(
        "ix_crawl_records_page_fetched",
        "crawl_records",
        ["page_id", "fetched_at"],
        unique=False,
    )

    op.create_table(
        "article_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("page_id", sa.Uuid(), nullable=False),
        sa.Column("crawl_id", sa.Uuid(), nullable=False),
        sa.Column("normalized_article_json", sa.JSON(), nullable=False),
        sa.Column("normalized_content_hash", sa.String(length=64), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("published_at", sa.String(length=40), nullable=True),
        sa.Column("modified_at", sa.String(length=40), nullable=True),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.CheckConstraint("version_number > 0", name="ck_article_versions_positive"),
        sa.ForeignKeyConstraint(
            ["crawl_id"],
            ["crawl_records.id"],
            name="fk_article_versions_crawl",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["page_id"],
            ["page_identities.id"],
            name="fk_article_versions_page",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "page_id",
            "normalized_content_hash",
            name="uq_article_versions_page_content_hash",
        ),
        sa.UniqueConstraint(
            "page_id",
            "version_number",
            name="uq_article_versions_page_version",
        ),
    )
    op.create_index(
        "ix_article_versions_page_version",
        "article_versions",
        ["page_id", "version_number"],
        unique=False,
    )

    op.create_table(
        "import_warnings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("crawl_id", sa.Uuid(), nullable=False),
        sa.Column("warning_code", sa.String(length=100), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "severity",
            sa.Enum(
                "warning",
                "fatal",
                name="stored_warning_severity",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("field_path", sa.String(length=500), nullable=True),
        sa.Column("source_location", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(
            ["crawl_id"],
            ["crawl_records.id"],
            name="fk_import_warnings_crawl",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_import_warnings_crawl",
        "import_warnings",
        ["crawl_id"],
        unique=False,
    )

    with op.batch_alter_table("page_identities") as batch_op:
        batch_op.create_foreign_key(
            "fk_page_identities_current_article_version",
            "article_versions",
            ["current_article_version_id"],
            ["id"],
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        )


def downgrade() -> None:
    """Remove the initial persistence schema in dependency-safe order."""
    with op.batch_alter_table("page_identities") as batch_op:
        batch_op.drop_constraint(
            "fk_page_identities_current_article_version",
            type_="foreignkey",
        )

    op.drop_index("ix_import_warnings_crawl", table_name="import_warnings")
    op.drop_table("import_warnings")
    op.drop_index("ix_article_versions_page_version", table_name="article_versions")
    op.drop_table("article_versions")
    op.drop_index("ix_crawl_records_page_fetched", table_name="crawl_records")
    op.drop_table("crawl_records")
    op.drop_index("ix_page_identities_normalized_url", table_name="page_identities")
    op.drop_table("page_identities")
