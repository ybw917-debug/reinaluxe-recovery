# Approved Knowledge to Content Opportunity Mapping

## Boundary

Stage 009B is an offline planning workflow:

```text
approved knowledge snapshot + authoritative 25-page context
  -> deterministic pending opportunities
  -> owner review and decisions
  -> hash-locked content change manifest
```

Approved knowledge is evidence, not automatic publication. No knowledge entry
flows directly into drafting, WordPress, or publication. The workflow performs
no network requests, database writes, redirects, canonical changes, URL
changes, merges, or article edits. Runtime artifacts belong under ignored
`data/community-intelligence/` and `data/content-operations/` paths.

## Immutable inputs

`community-build-snapshot` accepts one or more Stage 009A knowledge-base
directories. It records every batch digest, rejects conflicting reuse of a
knowledge ID, preserves qualifications, and produces byte-stable sorted
artifacts. Stale, contradicted, pending, and do-not-publish entries are
excluded. Internal-only entries are retained in a separate index and never in
the publishable snapshot. Opaque audit IDs may remain, but restricted source
identity, excerpts, aliases, and private provenance are not exported.

`content-build-page-context` combines the final page-role matrix, final finding
register, final roadmap, drafting-readiness record, and current Article
versions. SQLite is opened in read-only immutable mode. The initial snapshot
must contain each of the 25 approved URLs exactly once, preserve all URLs,
represent seven clusters, retain the older Chanel page as `Reposition`, and
contain no final `Merge` role. The final role matrix is authoritative over
keyword coincidence.

## Transparent mapping order

The mapper uses explicit normalized fields and no learned or opaque score.
Its priority is:

1. reject publishable use of stale, contradicted, or unbounded temporal claims;
2. keep internal-only knowledge in `internal_only_research` or `no_action`;
3. separate authentication, buying/commercial, and styling intent;
4. prefer an exact model and compatible page role over a broad brand match;
5. prefer an exact material and compatible role within the matching entity;
6. require dated page scope for annual, trend, current, or forecast knowledge;
7. use cluster, hub/supporting relationships, blockers, and approved operations
   to explain placement and change type;
8. flag equal-strength mappings and overlap as owner-review risks.

There are no embeddings, external models, online APIs, search-result inputs,
automatic LLM classification, or undocumented weights.

## Scope and page ownership policy

Narrow claims retain narrow model, material, region, specimen, and temporal
scope. Supplier-confirmed knowledge requires its approved attribution or scoped
wording; a supplier label is never converted into a universal claim.
Required qualifications travel unchanged with every opportunity.

Model-specific pages receive model-specific detail. A hub may receive a short
summary-and-route opportunity while its supporting page retains detailed
ownership. Hubs do not absorb all cluster evidence. Authentication evidence
does not automatically enter buying pages, and buying or tier guidance does
not automatically enter authentication pages. Styling maps only when styling
is a genuine next user task.

An approved correction claim may create a correction or qualification
opportunity; conflicting or ambiguous knowledge never creates an automatic
approval. Stale knowledge cannot create a drafting task. When an existing page
can clearly absorb knowledge without intent conflict, it suppresses a new
article candidate. A new article requires a distinct user question plus an
explanation of current-page ownership gaps, likely cluster, collision risks,
evidence sufficiency, and temporal durability.

## Outputs

`community-map-opportunities` writes pending JSONL/CSV opportunities plus
separate existing-page, new-article, internal-only, and no-action views. Every
mapping contains its evidence signals, page-role compatibility, rationale,
scope, qualification, dependencies, conflicts, and overlap risk. It contains
no proposed article wording and pre-approves nothing.
