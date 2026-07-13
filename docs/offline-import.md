# Offline Content Import

## Safety boundary

The importer reads only owner-provided local HTML or JSON. It contains no HTTP
client, DNS lookup, browser automation, JavaScript execution, crawler queue,
database write, or external service integration.

The source URL is used only to validate provenance, resolve relative links,
and classify links as internal or external.

## HTML selection rules

Parsing uses BeautifulSoup's standard-library `html.parser` backend. Selection
is deterministic:

1. Use the first semantic `article` element when present.
2. Otherwise use the first `main` element.
3. Otherwise inspect the document body.

Choosing one container prevents duplicate extraction when `article` and `main`
overlap. Within that container, semantic navigation, footer, aside, scripts,
styles, templates, hidden content, tested cookie banners, and elements with
navigation/content-info roles are excluded. Editorial content is not removed
merely because it has a broad styling class.

## Extraction rules

- Whitespace is collapsed consistently before validation.
- The document title comes from `title`, falling back only to an explicit H1.
- H1, H2, and H3 elements create sections in document order.
- Visible paragraphs, images, HTTP(S) links, and `details`/`summary` FAQs attach
  to the current section.
- Relative canonical, image, and link URLs resolve against the supplied source
  URL. Other URL schemes are ignored with warnings.
- Internal links share the supplied source hostname; other HTTP(S) links are
  external.
- Canonical URL, meta description, HTML language, publication date, and
  modification date are retained only when explicitly present and valid.
- Publication and modification timestamps must include a timezone.
- JSON-LD scripts are decoded as data and never executed. Malformed or
  non-object blocks generate warnings and do not abort visible-content import.
- Word count is derived from normalized headings, paragraphs, and visible FAQ
  text.
- The exact in-memory HTML string is preserved on `CrawlSnapshot` and hashed.

The importer deliberately uses `unknown` search intent, `other` content type,
and `unknown` article status. These values acknowledge the required domain
fields without claiming an unsupported classification.

## Command line

Run the project command through the uv-managed environment:

```console
uv run reinaluxe-recovery import-html article.html \
  --source-url https://owner.example/article/ \
  --fetched-at 2026-07-14T12:00:00+08:00 \
  --output import-result.json
```

Omit `--output` to print validated `ImportResult` JSON. The command never
accesses the source URL and never writes to a database.

Exit codes:

- `0`: normalization succeeded;
- `1`: content produced a controlled fatal import result;
- `2`: input validation, file reading, or output writing failed.

## Fixture-based use

`JsonFixtureInput` supports reproducible HTTP observations stored as local
JSON. Application code can validate a fixture with `load_json_fixture()` and
pass it to `import_json_fixture()`. This path uses the same parser and
normalizer as standalone HTML.

## Explicit exclusions

This boundary does not implement live crawling, persistence, SQLAlchemy
models, similarity or scoring, SEO conclusions, LLM calls, content rewriting,
publishing, WordPress, Reddit, Pinterest, dashboards, or business automation.
