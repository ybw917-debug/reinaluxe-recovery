# Deterministic Article Structure Audit

`audit-articles` reads persisted normalized `Article` versions through detached
Pydantic DTOs. It never reparses HTML, changes the database, contacts a URL, or
mutates an Article. Current versions are selected by default; `--all-versions`
selects history. Page, rule, information-severity, and count filters are
deterministic.

Findings are factual observations or explicitly labelled candidates. They are
audit heuristics, not Google penalties, ranking diagnoses, readability scores,
AI-content detection, or rewrite advice. Internal targets are broken-link
candidates only when absent from local inventory. External URLs are never
claimed broken because no URL is fetched. Cross-page similarity is deferred.

Results are ordered by page URL, version ID, severity (error, warning, info),
rule code, and evidence field. Finding IDs derive from version, rule, and
location. Counts derive from findings. Results are never persisted.

## CLI and exit policy

Options are `--database`, `--all-versions`, repeatable `--page-url`, repeatable
`--rule`, `--include-info/--exclude-info`, `--limit`, `--json`, `--output`, and
`--fail-on-errors`. Existing output files are refused.

- `0`: completed (including errors unless `--fail-on-errors` is set)
- `1`: completed with error findings and `--fail-on-errors`
- `2`: option, filter value, or output error
- `3`: database initialization or migration failure
- `4`: query, stored-payload validation, or audit-system failure
- `5`: no matching Article versions

One malformed stored payload causes a controlled audit-system error without any
write or partial stored result. ORM objects never cross the repository boundary.
