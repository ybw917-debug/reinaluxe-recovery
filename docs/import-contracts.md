# Offline Import Contracts

## Purpose

Sprint 1 Issue 003 defines a versioned, deterministic boundary between
owner-provided local content and the existing Content Audit domain contracts.
It does not fetch URLs. The supplied URL and timestamp are provenance values,
not instructions to access a website.

## Input contracts

### `HtmlFileInput`

A standalone HTML file cannot prove where or when it was fetched. The contract
therefore requires:

- `html_path`: an existing readable local file;
- `source_url`: a validated HTTP(S) URL supplied by the owner;
- `fetched_at`: a timezone-aware timestamp supplied by the owner;
- optional response headers when they are known.

No HTTP status is invented. Its `CrawlSnapshot` records a message explaining
that the status was unavailable while retaining the supplied HTML.

### `JsonFixtureInput`

A structured fixture requires a validated source URL, timezone-aware fetch
timestamp, HTTP status from 100 through 599, string headers, and an HTML body.
Unknown fields are rejected by the same strict Pydantic convention used by the
domain layer.

## Intermediate contract

`ParsedDocument` holds explicit metadata and normalized visible components
before domain identifiers and order values are assigned. It includes:

- the exact HTML string and its SHA-256 hash;
- source provenance from the input contract;
- explicit title, H1, language, canonical, description, and dates when valid;
- ordered sections with headings, paragraphs, images, links, and visible FAQs;
- defensively decoded JSON-LD objects;
- non-fatal extraction warnings.

It contains no inferred author, topic, entity, intent, publication date, or SEO
classification.

## Output contract

`ImportResult` uses contract version `1.0` and contains:

- `status`: `succeeded` or `failed`;
- the input source type;
- one validated `CrawlSnapshot`;
- one validated `Article` on success, otherwise `null`;
- warnings, including fatal diagnostics;
- the stable source hash;
- field-level provenance records.

A successful result must contain an article. A failed result cannot contain an
article. The envelope round-trips through Pydantic JSON validation.

## Provenance and deterministic identity

`FieldProvenance` labels values as `input`, `extracted`, `normalized`, or
`derived`. Direct HTML observations remain distinct from whitespace or URL
normalization and from derived word counts and hashes.

The raw HTML string is hashed as UTF-8 with SHA-256. Snapshot, article,
section, and component UUIDs are UUIDv5 values derived from that hash, the
supplied URL and timestamp, and a stable structural position. Re-importing the
same observation produces the same hashes and IDs without colliding with an
identical HTML body supplied for a different page.

## Warning and failure contract

`ImportWarning` has a stable code, severity, message, and optional source
location. Recoverable problems such as malformed JSON-LD or invalid optional
metadata have `warning` severity. Missing title, explicit language, or usable
editorial body has `fatal` severity and produces a failed result with the raw
snapshot preserved.

Input-schema violations, unreadable files, and invalid output locations remain
boundary errors. The CLI reports them with exit code 2; controlled content
failures use exit code 1.
