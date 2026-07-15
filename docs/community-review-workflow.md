# Community Owner Review Workflow

## Export the queue

```powershell
uv run reinaluxe-recovery community-export-review `
  --input data\community-intelligence\imports\batch-001 `
  --output data\community-intelligence\reviews\batch-001
```

The CSV and JSON queue show atomic wording, entity/time scope, retained source
excerpt, evidence type and summary, source independence, likely duplicates,
possible conflicts, and current evidence support. Suggested and owner decision
fields are blank. Nothing is pre-approved.

## Record and apply decisions

For each non-pending row, enter `owner_decision`, `owner_rationale`, `reviewer`,
a timezone-aware `reviewed_at`, `support_level`, and `publication_status`.
Qualification and follow-up fields are conditional. Leave `owner_decision`
blank to retain the claim as pending.

```powershell
uv run reinaluxe-recovery community-apply-decisions `
  --review data\community-intelligence\reviews\batch-001\claim-review-queue.csv `
  --input data\community-intelligence\imports\batch-001 `
  --output data\community-intelligence\decisions\batch-001
```

Invalid enum values, unknown claim IDs, missing reviewer metadata, and
conflicting duplicate rows fail before decision artifacts are written.
Rejected and contradicted claims remain in audit CSVs; sources are never
deleted. The decision directory includes immutable copies of normalized inputs
so the next stage is self-contained and reproducible.

## Build approved knowledge

```powershell
uv run reinaluxe-recovery community-build-kb `
  --input data\community-intelligence\decisions\batch-001 `
  --output data\community-intelligence\kb\batch-001
```

Only `approved` and `approved_with_qualification` decisions create entries.
Required qualifications, evidence/source IDs, scope, time range, reviewer, and
support level are preserved. Supplier-backed entries remain internal unless an
owner explicitly approves a publishable summary. The exports contain opaque
audit IDs but never source excerpts, aliases, or confidential provenance.

`publishable` is not publication. Article and WordPress changes require a
separate owner-controlled workflow outside Stage 009A.
