# Idempotency and Versioning

## Normalized content hash

Article version identity uses SHA-256 over UTF-8 canonical JSON with sorted
object keys, compact separators, and Unicode preserved. The payload includes
all editorial content and classification fields remaining on `Article`,
including title, URLs, lifecycle status, content type, language, search intent,
canonical URL, publication metadata, description, word count, ordered sections
and components, schema payloads, and topic relationships.

The hash excludes transport or generated identity data that must not create a
new editorial version:

- top-level `id`, `source_snapshot_id`, `normalized_at`, and
  `source_content_hash`;
- generated nested `id` values;
- generated `source_section_id` pointers.

It hashes the validated Article payload, not an ORM serialization. Identical
normalized editorial content therefore produces the same hash across crawl
times and source snapshots. A meaningful included-field change produces a
different hash.

## Decision table

| Observation | Page | Crawl | Article version |
| --- | --- | --- | --- |
| First successful import | Created | Created | Version 1 created |
| Same page, fetch time, and source hash | Reused | Reused | Reused |
| New crawl, unchanged content hash | Reused | Created | Existing version reused |
| New crawl, changed content hash | Reused | Created | Next version created |
| Contract-valid failed import | Created or reused | Created or reused | Failed; none created |

Warnings belong to a crawl. An exact repeat reuses the crawl and does not add
warning rows. A new crawl stores its own warnings even when Article content is
unchanged.

## Version sequence and current pointer

New versions use the current maximum page version plus one. The database
uniqueness constraints on `(page_id, version_number)` and
`(page_id, normalized_content_hash)` are the final integrity boundary.

The service flushes a new Article version before assigning
`current_article_version_id`, and both operations remain in the same
transaction. Failed and unchanged-content imports do not rewrite the pointer.
If an error occurs after the Article flush but before pointer update, the whole
transaction rolls back.

## Observation timestamps

For every newly persisted crawl, `first_seen_at` becomes the minimum observed
fetch time and `last_seen_at` becomes the maximum. Importing an older historical
crawl after a newer one can move `first_seen_at` backward, but it never reduces
`last_seen_at`. Exact repeated crawls do not create new history.

## Transactions and concurrency

One service call uses one synchronous SQLAlchemy transaction. Repositories do
not commit. Any escaping exception rolls back all writes for that import.

SQLite serializes writes and offers less concurrent-write flexibility than a
server database. Stage 004B performs deterministic pre-write lookups and relies
on unique constraints as the final race boundary. A constraint race is reported
as `PersistenceConflictError` so a future application layer may retry the whole
unit of work deliberately; unexpected integrity or database failures are not
suppressed.
