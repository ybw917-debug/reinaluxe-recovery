# Local Database Schema

## Purpose

Stage 004A defines the SQLite storage shape for validated offline content
imports. SQLAlchemy models are internal infrastructure. Existing Pydantic
domain and import contracts remain the application boundary.

## Tables

### `page_identities`

One row identifies one canonical page and anchors its history.

- UUID primary key
- unique required canonical URL
- indexed normalized URL
- first-seen and last-seen UTC timestamps
- nullable current article-version reference
- created and updated UTC timestamps

The canonical URL is the durable identity key. URL normalization and page-ID
selection belong to Stage 004B, not to the schema.

### `crawl_records`

One row preserves one raw offline import observation.

- UUID primary key and required page foreign key
- fetched UTC timestamp and optional HTTP status
- response headers JSON
- 64-character source HTML hash
- optional raw HTML
- controlled import status
- fatal diagnostics JSON
- created UTC timestamp

The unique `(page_id, fetched_at, source_html_hash)` constraint is the database
foundation for later idempotent writes. Stage 004A does not implement the
decision workflow that uses it.

### `article_versions`

One row preserves one validated normalized Article payload.

- UUID primary key
- required page and source-crawl foreign keys
- complete normalized Article JSON
- 64-character normalized-content hash
- positive sequential version number
- optional publication and modification timestamps
- created UTC timestamp

Page/version and page/content-hash pairs are independently unique. Detailed
headings, paragraphs, images, links, FAQs, and entities remain inside validated
JSON rather than being prematurely duplicated into relational tables.

### `import_warnings`

One row preserves one warning or fatal diagnostic for a crawl record.

- UUID primary key and required crawl foreign key
- warning code, message, and controlled severity
- optional field path and source location
- created UTC timestamp

## Relationships and deletion policy

A page owns crawl and article-version history. A crawl owns warning history and
may source article versions. The page's current-version pointer is nullable so
a page can exist before normalized content is available.

All foreign keys use `RESTRICT`. ORM relationships permit save/update and merge
but do not configure delete cascades. Deleting historical records is not a
normal business operation, and accidental parent deletion must not erase audit
history.

The page/current-version reference and article/page reference form a logical
cycle. The initial SQLite migration creates the history tables first and then
adds the current-version foreign key with Alembic batch mode. Downgrade removes
that pointer before dropping the history tables.

## Timestamp policy

Every persistence datetime must be timezone-aware. The `UTCDateTime` SQLAlchemy
type rejects naive values, converts aware values to UTC, stores ISO 8601 text
with an explicit offset, and restores aware UTC datetimes. This avoids SQLite's
loss of timezone information.

## Local-data policy

The eventual default database is `data/reinaluxe-recovery.db`. The repository
already ignores `data/`, `*.db`, `*.sqlite`, and `*.sqlite3`. Tests use only
temporary directories and do not create a repository-local database.
