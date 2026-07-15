# Offline Community Intelligence

## Stage 009A boundary

Stage 009A is a second, isolated workstream. It turns owner-provided local
records into a human-reviewed evidence knowledge base:

```text
source record -> atomic candidate claim -> evidence bundle
              -> owner review decision -> approved knowledge entry
```

A candidate claim is not a fact. Import never verifies, approves, publishes,
or updates an article. The workflow does not open the site-recovery SQLite
database and does not call acquisition, WordPress, a browser, an LLM, an
embedding service, or any network client. Runtime data belongs only under
`data/community-intelligence/`, which is Git-ignored. Sanitized tests remain
under `tests/`.

## Public contracts

The existing public `CommunityClaim`, `EvidenceReference`,
`HumanReviewDecision`, `EntityMention`, `Topic`, and `RecoveryRecommendation`
concepts were retained. Stage 009A extends the same public domain boundary with
workflow-specific, version `1.0` contracts:

- `CommunitySourceRecord` retains minimal source provenance and excerpt;
- `AtomicCandidateClaim` holds exactly one independently reviewable statement;
- `EvidenceRecord` states what evidence supports, its scope, and confidentiality;
- `ClaimReviewDecision` records explicit human judgment;
- `ApprovedKnowledgeEntry` is created only from an approved decision.

The new names represent distinct workflow stages rather than duplicate aliases
for the existing article-audit records. They remain immutable Pydantic models
and use IDs for relationships.

## Determinism and duplicate handling

Unicode is normalized with NFKC, whitespace is collapsed, language tags and
platform labels are normalized, URLs are canonicalized without fetching, and
timestamps are normalized to UTC. Canonical sorted JSON is SHA-256 hashed.
Generated IDs use a readable prefix plus the first 24 hash characters.

Exact duplicate sources and claims are reported and safely consolidated under
their stable identity. Likely claim duplicates use a documented token Jaccard
comparison within matching entity scope. The queue shows the score and shared
tokens; likely matches are never merged. Possible conflicts are also queue
hints, never automatic truth judgments.

## Scope boundaries

Claims must preserve product/entity scope, market, batch or factory label, and
valid time limits when known. A later observation does not silently generalize
to every model, variant, region, factory, or period. Stale and contradicted
decisions remain auditable and are excluded from knowledge export.

Stage 009A contains no live community data acquisition. Any later collection
stage must prohibit login automation, CAPTCHA bypass, rate-limit evasion,
account farming, and private-community collection.
