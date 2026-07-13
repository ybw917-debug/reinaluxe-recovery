# Content Audit Domain Model

## Purpose

This document defines the stable domain vocabulary for Sprint 1 Issue 002. The
models describe content, provenance, audit observations, recommendations, human
judgment, and time-bounded snapshots. They do not crawl websites, calculate SEO
scores, infer search-engine penalties, or automate editorial actions.

## Contract conventions

- Top-level records use contract version `1.0`.
- Entity IDs and relationships use UUIDs. IDs may be generated when a model is
  constructed, but serialized records preserve them.
- Timestamps use timezone-aware ISO 8601 datetimes. Reporting periods use dates.
- Web locations use Pydantic `HttpUrl` values.
- Models are immutable, reject unknown fields, strip surrounding string
  whitespace, and validate defaults.
- Relationships use IDs so storage and transport choices can change later.
- Raw crawl content never appears on normalized `Article` records.
- Community statements never become `EvidenceReference` records merely because
  they were collected.
- Risk assessments and recommendations remain separate from
  `HumanReviewDecision` records.

## Content concepts

### 1. Article

- **Purpose:** Normalized representation of one content page derived from a raw
  crawl snapshot.
- **Required fields:** `source_snapshot_id: UUID`, `url: HttpUrl`,
  `title: str`, `status: ArticleStatus`, `content_type: ContentType`,
  `language: str`, `normalized_at: AwareDatetime`, and
  `search_intents: list[SearchIntent]`.
- **Optional or defaulted fields:** `contract_version: Literal["1.0"]`,
  generated `id: UUID`, canonical URL, publication/modification timestamps,
  SHA-256 source hash, meta description, word count, sections, schema markup,
  topic IDs, and topic-cluster IDs.
- **Validation:** URLs must be HTTP(S), language uses a compact language-code
  form, timestamps must be timezone-aware, the source hash must be lowercase
  SHA-256, search intents and section order values must be unique, modification
  cannot precede publication, and draft/published articles require content.
- **Relationships:** References one `CrawlSnapshot`; contains
  `ContentSection` and `SchemaMarkup`; references `Topic` and `TopicCluster`.
- **Extensibility:** New optional normalized metadata can be added without
  placing raw HTML, performance metrics, or generated recommendations here.

### 2. Heading

- **Purpose:** Ordered heading extracted from normalized source content.
- **Required fields:** `level: int`, `text: str`, and `order: int`.
- **Optional or defaulted fields:** Generated `id: UUID` and `anchor: str`.
- **Validation:** Level is 1–6, text is non-empty, and order is non-negative.
- **Relationships:** Embedded by a `ContentSection`.
- **Extensibility:** Future source offsets or accessibility metadata may be
  added without changing section identity.

### 3. ContentSection

- **Purpose:** Ordered container for the typed components of one article
  section.
- **Required fields:** `order: int`.
- **Optional or defaulted fields:** Generated `id: UUID`, optional `heading`,
  and lists of paragraphs, images, links, FAQ items, and entity mentions.
- **Validation:** Order is non-negative; nested objects validate independently.
- **Relationships:** Embedded by `Article`; contains `Heading`, `Paragraph`,
  `Image`, `Link`, `FAQItem`, and `EntityMention`.
- **Extensibility:** Additional component collections can be introduced without
  flattening content into untyped text.

### 4. Paragraph

- **Purpose:** Normalized paragraph with optional traceability to source text
  offsets.
- **Required fields:** `text: str` and `order: int`.
- **Optional or defaulted fields:** Generated `id: UUID` and paired
  `source_start_offset`/`source_end_offset` integers.
- **Validation:** Text is non-empty, order and offsets are non-negative, offsets
  must be supplied together, and the end cannot precede the start.
- **Relationships:** Embedded by `ContentSection`.
- **Extensibility:** Future text annotations can reference the paragraph ID and
  offsets rather than rewriting source content.

### 5. Image

- **Purpose:** Image reference observed in normalized source content.
- **Required fields:** `source_url: HttpUrl` and `order: int`.
- **Optional or defaulted fields:** Generated `id: UUID`, alt text, caption,
  width, and height.
- **Validation:** URL must be HTTP(S), order is non-negative, and dimensions are
  positive when supplied.
- **Relationships:** Embedded by `ContentSection`.
- **Extensibility:** Asset hashes, licensing facts, or accessibility review can
  be added as separate optional metadata.

### 6. Link

- **Purpose:** Link observed in normalized article content.
- **Required fields:** `target_url: HttpUrl`, `link_type: LinkType`, and
  `order: int`.
- **Optional or defaulted fields:** Generated `id: UUID`, anchor text, and
  `rel: list[str]`.
- **Validation:** URL must be HTTP(S) and order is non-negative.
- **Relationships:** Embedded by `ContentSection`.
- **Extensibility:** Future link-health observations should reference link IDs
  rather than mutate the source link contract.

### 7. SchemaMarkup

- **Purpose:** Preserve a structured-data payload independently from any
  validation findings.
- **Required fields:** `schema_type: SchemaType` and
  `payload: dict[str, JsonValue]`.
- **Optional or defaulted fields:** Generated `id: UUID`, source section ID, and
  validation-error strings.
- **Validation:** Payload must be JSON-compatible and schema type is controlled.
- **Relationships:** Embedded by `Article`; may reference a `ContentSection`.
- **Extensibility:** New schema types and external validator results can be
  added without introducing SEO conclusions.

### 8. FAQItem

- **Purpose:** Question-and-answer pair present in source content.
- **Required fields:** `question: str`, `answer: str`, and `order: int`.
- **Optional or defaulted fields:** Generated `id: UUID`.
- **Validation:** Question and answer are non-empty; order is non-negative.
- **Relationships:** Embedded by `ContentSection`; may also be represented by
  separate FAQ schema markup.
- **Extensibility:** Similarity or quality findings should reference the FAQ ID
  and remain outside the source record.

### 9. EntityMention

- **Purpose:** Named entity mention preserved with its local source context.
- **Required fields:** `name: str`.
- **Optional or defaulted fields:** Generated `id: UUID`, entity type, source
  text, source section ID, and evidence-reference IDs.
- **Validation:** Name is non-empty and bounded context fields reject oversized
  values.
- **Relationships:** Embedded by `ContentSection`; may reference factual
  `EvidenceReference` records.
- **Extensibility:** Entity resolution, aliases, or external knowledge IDs can
  be added later without treating a mention as verified fact.

### 10. Topic

- **Purpose:** Stable editorial subject used to classify content.
- **Required fields:** `name: str`.
- **Optional or defaulted fields:** Generated `id: UUID`, description, parent
  topic ID, and aliases.
- **Validation:** Name is non-empty.
- **Relationships:** Can form a parent-child hierarchy; referenced by `Article`,
  `TopicCluster`, and `CommunityClaim`.
- **Extensibility:** External taxonomy IDs and lifecycle metadata can be added
  without changing article content.

### 11. TopicCluster

- **Purpose:** Group related topics and articles around a primary topic.
- **Required fields:** `name: str`, `primary_topic_id: UUID`, and non-empty
  `topic_ids: list[UUID]`.
- **Optional or defaulted fields:** Generated `id: UUID`, article IDs, and
  description.
- **Validation:** Topic IDs are unique and include the primary topic.
- **Relationships:** References `Topic` and `Article` IDs.
- **Extensibility:** Cluster strategy, owner status, and hub-candidate metadata
  can be added without making a recovery decision automatic.

### 12. SearchIntent

- **Purpose:** Controlled statement of the human goal an article may serve.
- **Required value:** One of `informational`, `commercial_investigation`,
  `transactional`, `navigational`, `mixed`, or `unknown`.
- **Optional fields:** None; it is a string enum.
- **Validation:** Unknown values are rejected and article intent lists are
  non-empty and unique.
- **Relationships:** Referenced by `Article`; similarity findings may use the
  `search_intent` scope.
- **Extensibility:** New values require an explicit contract revision; intent
  must not be inferred as a ranking fact.

## Evidence and judgment concepts

### 13. EvidenceReference

- **Purpose:** Traceable factual evidence used by derived findings,
  assessments, recommendations, or human decisions.
- **Required fields:** `source_type: EvidenceSourceType`, `source_name: str`,
  `supports: str`, `observed_at: AwareDatetime`,
  `collected_at: AwareDatetime`, and `confidence: EvidenceConfidence`.
- **Optional or defaulted fields:** Generated `id: UUID`, source URL, source
  record ID, excerpt, primary-source flag, notes, article IDs, and snapshot IDs.
- **Validation:** At least one source locator is required; collection cannot
  precede observation; community is deliberately not an evidence-source enum.
- **Relationships:** Referenced by findings, assessments, recommendations,
  entity mentions, community-claim corroboration, and human decisions.
- **Extensibility:** Evidence signatures, retention policy, or external source
  metadata can be added while retaining the stable evidence ID.

### 14. CommunityClaim

- **Purpose:** Preserve a community statement without promoting it to factual
  evidence.
- **Required fields:** `statement: str`, `source_platform: str`, and
  `collected_at: AwareDatetime`.
- **Optional or defaulted fields:** Generated `id: UUID`, verification status
  defaulting to `unverified`, source URL/record ID, author alias, posted time,
  context, corroborating evidence IDs, article IDs, and topic IDs.
- **Validation:** A source locator is required; collection cannot precede
  posting; `corroborated` or `contradicted` requires factual evidence IDs.
- **Relationships:** May reference `Article`, `Topic`, and separately stored
  `EvidenceReference` records.
- **Extensibility:** Moderation or consent metadata may be added later; the
  claim remains a distinct type regardless of source platform.

### 15. HumanReviewDecision

- **Purpose:** Record explicit owner/reviewer judgment separately from generated
  recommendations.
- **Required fields:** `article_id: UUID`, `reviewer_id: str`,
  `decision: ReviewDecision`, `decided_at: AwareDatetime`, and `rationale: str`.
- **Optional or defaulted fields:** Generated `id: UUID`, recommendation ID,
  approved action, evidence IDs, community-claim IDs, and superseded decision ID.
- **Validation:** Approved decisions require an approved action; other decision
  states cannot contain one.
- **Relationships:** References an `Article`, optionally a
  `RecoveryRecommendation`, provenance records, and an earlier decision.
- **Extensibility:** Reviewer roles, approval stages, and signatures can be
  added without placing owner judgment on an automated assessment.

## Audit concepts

### 16. SimilarityFinding

- **Purpose:** Store an evidence-backed overlap observation produced elsewhere,
  without implementing the comparison method.
- **Required fields:** Subject and compared article UUIDs,
  `scope: SimilarityScope`, `observed_at: AwareDatetime`, `summary: str`,
  `method_name: str`, and non-empty evidence-reference IDs.
- **Optional or defaulted fields:** Generated `id: UUID`, method version,
  method-specific similarity score, section IDs, and limitations.
- **Validation:** Articles must differ and an optional score is constrained to
  0–1.
- **Relationships:** References two `Article` records, optional sections, and
  factual evidence; referenced by `ContentRiskAssessment`.
- **Extensibility:** Method parameters may be versioned externally. No threshold
  or scoring formula is encoded in this contract.

### 17. ContentRiskAssessment

- **Purpose:** Represent an automated evidence-backed risk description that is
  not an owner-approved judgment.
- **Required fields:** `article_id: UUID`, `assessed_at: AwareDatetime`,
  `risk_level: RiskLevel`, non-empty `categories: list[RiskCategory]`,
  `summary: str`, `assessor: str`, and non-empty evidence-reference IDs.
- **Optional or defaulted fields:** Generated `id: UUID`, similarity-finding
  IDs, separately identified community-claim IDs, methodology version, and
  limitations.
- **Validation:** Risk categories are unique and the containing output contract
  rejects dangling provenance references.
- **Relationships:** References one `Article`, factual evidence, similarity
  findings, and separately typed community claims; referenced by recommendations.
- **Extensibility:** New qualitative categories can be added deliberately. AI
  probability, assumed penalties, and causal ranking claims are excluded.

### 18. RecoveryRecommendation

- **Purpose:** Generated editorial proposal separated from source content and
  human approval.
- **Required fields:** `article_id: UUID`, `assessment_id: UUID`,
  `action: RecoveryAction`, `created_at: AwareDatetime`, `rationale: str`,
  `priority: RiskLevel`, and non-empty evidence-reference IDs.
- **Optional or defaulted fields:** Generated `id: UUID`,
  `requires_human_review: Literal[True]`, target article IDs, proposed changes,
  constraints, and expiration time.
- **Validation:** Merge actions require targets; targets are unique and exclude
  the source article; expiration cannot precede creation.
- **Relationships:** References an `Article`, `ContentRiskAssessment`, factual
  evidence, and optional target articles; may be reviewed by
  `HumanReviewDecision`.
- **Extensibility:** Workflow state or cost estimates can be added later, but
  publishing or owner approval must remain outside this model.

## Snapshot concepts

### 19. CrawlSnapshot

- **Purpose:** Immutable raw observation produced by a future crawler, kept
  separate from normalized audit content.
- **Required fields:** `requested_url: HttpUrl`,
  `captured_at: AwareDatetime`, and `source_system: str`.
- **Optional or defaulted fields:** `contract_version: Literal["1.0"]`,
  generated `id: UUID`, final URL, status, headers, redirects, raw HTML,
  response content type, SHA-256 content hash, observed canonical URL, robots
  observation, duration, and error message.
- **Validation:** At least an HTTP status or fetch error is required; URLs,
  timestamps, hash, status range, and duration are validated.
- **Relationships:** Referenced by `Article` and `EvidenceReference` IDs.
- **Extensibility:** Transport diagnostics can be added without placing
  normalized sections or audit conclusions in the raw record.

### 20. PerformanceSnapshot

- **Purpose:** Time-bounded observation of page-level or site-level metrics.
- **Required fields:** `scope: MetricScope`,
  `source_type: EvidenceSourceType`, `captured_at: AwareDatetime`,
  `period_start: date`, and `period_end: date`.
- **Optional or defaulted fields:** `contract_version: Literal["1.0"]`,
  generated `id: UUID`, article ID, page URL, clicks, impressions, CTR, average
  position, indexed state, custom numeric metrics, and dimensions.
- **Validation:** Periods are ordered; page scope requires a page/article
  locator; site scope forbids both; at least one metric is required.
- **Relationships:** Page snapshots may reference an `Article`; factual use in
  an assessment is mediated through an `EvidenceReference`.
- **Extensibility:** Additional metrics belong in `custom_metrics` until a
  stable first-class field is justified. Page and site scopes never mix.

## Output envelope

`ContentAuditResult` is the versioned output contract. It contains one risk
assessment, one or more recommendations, and distinct collections of evidence,
community claims, similarity findings, and human decisions. Its validation
ensures every referenced ID resolves inside the envelope and every nested
article ID matches the audited article.

The envelope preserves provenance; it does not assert that an assessment is
correct, that a recommendation is approved, or that a search-engine penalty
exists.
