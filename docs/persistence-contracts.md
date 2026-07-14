# Persistence Contracts

## Boundary

Stage 004B stores validated offline `ImportResult` records. The Pydantic domain
and importing models remain the source of truth. SQLAlchemy models never leave
the persistence package; repository and service callers receive immutable,
strict Pydantic DTOs.

`ImportPersistenceService.save_import_result()` owns one transaction for one
import. Repositories accept an existing `Session`, perform reads only, never
commit, and return detached values.

## Page identity

Successful imports choose the page URL in this order:

1. `Article.canonical_url` when present;
2. `Article.url` otherwise.

Failed imports have no Article, so diagnostic history uses the first available
value from `CrawlSnapshot.observed_canonical_url`, `final_url`, and
`requested_url`.

The selected URL passes through one offline normalization boundary:

- scheme and host are lowercased;
- HTTP port 80 and HTTPS port 443 are removed;
- fragments are removed;
- an empty path becomes `/`;
- path case and the exact query string are preserved;
- only absolute HTTP(S) URLs without user information are accepted.

The boundary does not fetch, resolve redirects, sort or remove query
parameters, alter path case, or apply speculative SEO canonicalization.

## DTOs

`PersistImportResult` reports IDs, component dispositions, version number,
normalized page URL, source and content hashes, warning count, persistence time,
and any controlled failure message. Component dispositions are `created`,
`reused`, `version_created`, or `failed`.

Read operations return:

- `StoredPageSummary`;
- `StoredCrawlSummary`;
- `StoredArticleVersionSummary`, containing a revalidated `Article`;
- `StoredImportWarningSummary`.

Every DTO round-trips through Pydantic v2 JSON. Raw SQLAlchemy objects are not a
public return type.

## Repository operations

`PersistenceRepository` provides:

- `get_page_by_url()` and `get_page_by_id()`;
- `list_pages()`;
- `get_crawl_record()` and `list_crawl_records()`;
- `get_latest_article()`, `list_article_versions()`, and
  `get_article_version()`;
- `list_import_warnings()`;
- `database_health_check()`.

Single-record reads return `None` when absent. Collection reads return an empty
list. Invalid URL inputs and database failures raise explicit persistence
exceptions.

## Failed imports

The Stage 004A schema explicitly supports failed crawl status, fatal diagnostic
JSON, pages without a current Article, and warning rows. Stage 004B therefore
persists a contract-valid failed `ImportResult` as page and crawl history.

A failed import persists all warnings and fatal diagnostics but never creates
an `ArticleVersion`, never sets or changes `current_article_version_id`, and
returns an article disposition of `failed`. An invalid cross-record contract,
such as mismatched source hashes or snapshot IDs, is rejected before writes.

## Error policy

All writes are flushed and committed by the service transaction boundary.
Injected or real errors roll back the page, crawl, warnings, Article version,
and pointer together. Database uniqueness conflicts are translated to an
explicit `PersistenceConflictError`; other database failures are not swallowed.

## Stage 004C lifecycle and application queries

`initialize_database()` and `upgrade_database()` call Alembic programmatically;
they never shell out. Lifecycle results report resolved path, redacted URL,
previous/current/target revisions, whether migration work occurred, and health.
Existing database files are upgraded in place and are never deleted or replaced.

`StoredPageInventorySummary` is the smallest compatible Stage 004C extension.
It adds current version number plus crawl and Article-version counts without
changing the database schema or exposing ORM rows. `PageInventoryResult` and
`PageDetails` are application-level Pydantic contracts used by the CLI. Detail
history contains detached crawl, Article-version, and warning DTOs.
