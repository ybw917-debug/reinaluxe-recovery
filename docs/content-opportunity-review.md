# Content Opportunity Owner Review

## Review queue

Create the owner queue from deterministic mapping artifacts:

```powershell
uv run reinaluxe-recovery community-export-opportunity-review `
  --input data\content-operations\opportunities\pilot-001 `
  --output data\content-operations\opportunity-reviews\pilot-001
```

Each row shows the approved knowledge text and qualification, support and
publication status, proposed target and page role, proposed location and type,
mapping rationale, entity and intent matches, overlap and paired-page risks,
and evidence and source-claim IDs. Owner fields are blank. No opportunity is
pre-approved.

## Owner decisions

Valid decisions are `approved`, `approved_with_changes`, `rejected`, `defer`,
`needs_more_evidence`, `duplicate`, `conflicts_with_page_role`,
`use_for_new_article`, `internal_only`, and `no_action`. A completed decision
must include reviewer, timezone-aware review time, rationale, and drafting
priority. Blank decisions remain pending.

The owner may change the target, type, or location. A changed page target must
exist in the locked page context. `use_for_new_article` removes the existing
page target but still requires later manifest validation. Required knowledge
qualifications may not be weakened or removed. Paired-page requirements and
follow-up questions should record unresolved coordination explicitly.

Apply the reviewed queue with:

```powershell
uv run reinaluxe-recovery community-apply-opportunity-decisions `
  --review data\content-operations\opportunity-reviews\pilot-001\opportunity-review-queue.csv `
  --input data\content-operations\opportunities\pilot-001 `
  --output data\content-operations\opportunity-decisions\pilot-001
```

Unknown opportunities, invalid targets, invalid vocabulary, tampered hashes,
and conflicting final rows fail before output is written. Internal-only
knowledge cannot be upgraded to publishable use. Rejected, deferred, and
pending rows remain auditable, and deterministic reruns produce the same
artifacts.

## Review policy

Page roles take precedence over keyword matching. Confirm that a narrow claim
stays narrow, the page owns the user intent, any hub/detail split is preserved,
and authentication remains distinct from commercial guidance. A new article
is appropriate only for a distinct user question that current pages cannot
own without collision. Approval authorizes inclusion in a later manifest; it
does not authorize drafting, publishing, URL changes, redirects, canonicals,
or merges.
