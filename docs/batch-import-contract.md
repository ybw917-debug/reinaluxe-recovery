# Batch Import Contract

## Purpose and format

`BatchManifest` version `1.0` describes an ordered set of owner-provided local
HTML observations. JSON is the only supported manifest format. Contracts are
immutable, reject unknown fields, and contain no instruction to fetch a URL.
`source_url` is provenance used by the existing offline parser.

See [the complete example](examples/batch-manifest.json).

## Manifest fields

- `contract_version`: required literal `"1.0"`;
- `batch_id`: required stable non-empty owner identifier;
- `created_at`: required timezone-aware ISO 8601 timestamp;
- `default_fetched_at`: optional timezone-aware observation timestamp;
- `default_headers`: optional string header mapping;
- `entries`: at least one ordered `BatchManifestEntry`;
- `metadata`: optional JSON metadata preserved on the source manifest.

Entry fields are `entry_id`, `html_path`, `source_url`, optional `fetched_at`,
`status_code` (default `200`), optional `headers`, `enabled` (default `true`),
optional `notes`, and optional lowercase SHA-256 `expected_source_hash`.

Entry IDs and file paths must be unique. Each entry must have its own
timezone-aware `fetched_at` or inherit `default_fetched_at`. Entry headers
override same-named manifest defaults. Source URLs must be absolute HTTP(S)
URLs, but are never opened.

## Path-security policy

`html_path` must be relative to the manifest directory. Absolute paths are not
supported. Before database lifecycle work, every entry path is resolved,
including symbolic links, and must remain inside that directory. `..` traversal
or any resolved escape invalidates the manifest.

Missing selected files are entry-level failures so continue-on-error can report
and proceed. Files are read as bytes and decoded with the existing `utf-8-sig`
import policy; the decoded HTML is not normalized or rewritten before parsing.

## Source-hash policy

When `expected_source_hash` is present, it is compared before parsing with the
same SHA-256 source hash produced by the existing importer over decoded UTF-8
HTML. A mismatch prevents parsing and persistence for that entry. The computed
hash is included in successful entry results.

## Result contracts

`BatchEntryResult` records identity and path provenance, entry status, import and
persistence success, existing persistence dispositions, Article version,
warnings, fatal diagnostics, error category/message, timestamps, duration, and
source hash.

`BatchImportResult` records the manifest/database provenance, ordered results,
overall status, and aggregate enabled/attempted/succeeded/failed/skipped plus
created/reused counts. Aggregates are derived from results rather than updated
as independent mutable counters. All contracts round-trip through Pydantic JSON.
