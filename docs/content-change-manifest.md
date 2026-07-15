# Content Change Manifest

## Purpose

`ContentChangeManifest` is the only permitted future input to content drafting.
It is built only after owner opportunity review and includes only `approved`
and `approved_with_changes` decisions. It contains planning constraints, not
article copy, and does not itself authorize WordPress or publication.

```powershell
uv run reinaluxe-recovery content-build-change-manifest `
  --decisions data\content-operations\opportunity-decisions\pilot-001 `
  --knowledge-snapshot data\community-intelligence\snapshots\pilot-001 `
  --page-context data\content-operations\page-context\inventory-025-v2 `
  --database data\reinaluxe-recovery.db `
  --output data\content-operations\change-manifests\pilot-001
```

## Locked authority

The manifest locks the knowledge snapshot ID and hash, page-context snapshot ID
and hash, each affected page identity, current Article version ID, page content
hash, and context hash. It records the exact approved opportunity IDs, allowed
knowledge IDs, approved change types, paired-page requirements, and required
qualifications verbatim. Rejected and deferred opportunity claim IDs become
prohibited claims rather than silently disappearing.

Creation fails when an approved opportunity or knowledge entry is missing,
knowledge is stale or contradicted, a qualification changes, a page target is
outside the context, or the read-only database no longer matches a locked
Article version and hash. A new-article candidate may omit a page target; every
other approved change requires a current context page.

## Drafting and validation constraints

A future drafting stage must:

- use only allowed knowledge IDs and approved change types;
- preserve model, material, region, specimen, and temporal scope;
- reproduce required qualifications exactly;
- honor hub/detail and other paired-page requirements;
- revalidate every knowledge, context, Article-version, and content hash;
- exclude prohibited claims and operations;
- obtain separate owner approval before any WordPress or publication action.

Automatic URL, redirect, canonical, merge, database mutation, drafting, and
publishing operations remain prohibited. If a locked input changes, rebuild
the page context, remap, and repeat owner review rather than bypassing the
stale-context failure.

## Outputs

The command writes the JSON manifest, affected-page and approved-knowledge
usage CSVs, human-readable drafting constraints and validation requirements,
and a summary proving that article copy and database writes were both zero.
