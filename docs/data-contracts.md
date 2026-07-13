# Content Audit Data Contracts

## Contract flow

```text
Raw observations             Normalized inputs             Derived outputs
---------------------------  ----------------------------  ---------------------------
CrawlSnapshot -------------> Article --------------------> SimilarityFinding
PerformanceSnapshot -------> EvidenceReference ----------> ContentRiskAssessment
CommunityClaim (separate) -------------------------------> RecoveryRecommendation
                                                           |
                                                           v
                                                HumanReviewDecision (separate)
```

The arrows express provenance and workflow, not implemented processing. Issue
002 defines data structures only.

## Boundary rules

### Raw crawl versus normalized content

- `CrawlSnapshot` may contain raw HTML, response headers, redirects, and fetch
  errors.
- `Article` contains normalized typed sections and references its source
  snapshot by UUID.
- Normalization must create a new record; it must not mutate the raw snapshot.
- A normalized article never embeds raw HTML.

### Factual evidence versus community claims

- `EvidenceReference` accepts controlled factual source types and requires a
  source locator, observation time, collection time, and confidence.
- `CommunityClaim` is a different model with an explicit verification state.
- `community` is intentionally not an `EvidenceSourceType` value.
- A community claim can become corroborated only by referencing separately
  stored factual evidence; its original statement and provenance remain intact.

### Automated assessment versus human judgment

- `ContentRiskAssessment` records an automated qualitative assessment and its
  limitations.
- `RecoveryRecommendation` always has `requires_human_review: true`.
- `HumanReviewDecision` records the owner's or reviewer's explicit action.
- An approved action is never inferred from a risk level or recommendation.

### Page metrics versus site metrics

- `PerformanceSnapshot.scope = "page"` requires a page URL or article ID.
- `PerformanceSnapshot.scope = "site"` rejects page URLs and article IDs.
- Metric movement is an observation, not evidence of its cause.
- Performance evidence must not be rewritten as a Google penalty claim.

### Source content versus recommendations

- Source text and components live on `Article` and its nested content objects.
- Proposed changes live on `RecoveryRecommendation`.
- No recommendation modifies source content, publishes output, or authorizes an
  editorial action.

## Input contracts

### Crawl input

`CrawlSnapshot` is the future crawler boundary. The current project does not
create snapshots. A caller must provide a timezone-aware capture time and either
an HTTP status or an error message.

### Normalized article input

`Article` is the primary audit input. It requires a source snapshot UUID and
contains typed sections. The complete executable example is:

- [Normalized article JSON](examples/normalized-article.json)

The example includes a heading, paragraph, image, link, FAQ item, entity
mention, schema payload, topic relationships, and search intent.

### Performance input

`PerformanceSnapshot` records one source, one reporting period, and one scope.
Site totals and page metrics must be sent as different snapshots.

## Output contract

`ContentAuditResult` is the versioned transport envelope. Required output:

- one audited article ID;
- at least one factual evidence reference;
- one content risk assessment;
- at least one recovery recommendation;
- optional, separately typed community claims;
- optional similarity findings;
- optional human review decisions.

The complete executable example is:

- [Risk assessment with evidence and recommendation JSON](examples/content-audit-result.json)

The example deliberately states limitations: it does not infer a search penalty
or causal ranking explanation, and its community claim remains unverified.

## Serialization

Use Pydantic JSON mode at contract boundaries:

```python
article_json = article.model_dump_json(indent=2)
article = Article.model_validate_json(article_json)
```

- UUIDs serialize as strings.
- Enums serialize to their controlled string values.
- URLs serialize as normalized HTTP(S) strings.
- Datetimes serialize with explicit timezone offsets.
- Unknown fields are rejected.

The examples are validated in the automated test suite and must continue to
round-trip without data loss.

## Provenance integrity

Inside `ContentAuditResult`:

- all evidence, claim, finding, and recommendation IDs are unique;
- assessment references must resolve inside the envelope;
- finding evidence must resolve inside the envelope;
- recommendation evidence and assessment IDs must resolve;
- review decisions may only reference recommendations in the same result;
- every nested article ID must match the audited article.

Dangling references make the entire contract invalid.

## Explicit exclusions

These contracts do not provide:

- crawler or parser execution;
- SQLAlchemy models, tables, or migrations;
- similarity algorithms, thresholds, or scoring formulas;
- AI-authorship probability;
- SEO or search-ranking causality;
- LLM prompts or calls;
- Reddit, WordPress, Pinterest, or dashboard integrations;
- automatic owner approval, publishing, archiving, merging, or rewriting.

## Versioning and extension policy

- Additive optional fields can remain within contract version `1.0` when they
  do not alter existing meaning.
- New enum values require deliberate review because consumers may use exhaustive
  matching.
- Removing, renaming, or changing a field's meaning requires a new contract
  version and migration guidance.
- New derived values must retain source IDs, method/version metadata, and known
  limitations.
