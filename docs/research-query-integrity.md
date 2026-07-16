# Research query integrity

Use `research-preview-queries` before a paid discovery run:

```console
uv run reinaluxe-recovery research-preview-queries \
  --request docs/examples/aaa-pillar-001.yaml \
  --query-families terminology,psp_qc,handmade_provenance \
  --output data/research/query-previews/aaa-pillar-001-smoke-v2
```

Preview mode is deterministic and offline. It does not construct a provider, call Zhipu, or run GLM analysis. It writes the exact provider query, requested lane, optional domain filter, topic anchors, exclusions, intentionally included article entities, generation inputs, and query hash. A failed query-quality record blocks the paid call.

The AAA retrieval defaults are:

- Reddit terminology: `site:reddit.com/r/ replica bags AAA 1:1 mirror quality superfake high tier meaning`, with `reddit.com` as the domain filter.
- Public PSP/QC discussion: `replica handbag "pre-shipment photos" PSP QC pictures received item lighting difference seller photos buyer forum review`.
- Expert provenance analysis: `replica handbag handmade "original leather" tannery claims "leather provenance" verification expert analysis`.

Quality has two independent gates. Structural quality covers anchors, entity contamination, lane strategy, duplicate risk, length, and the presence of a research question. Retrieval quality covers research-question/lane consistency, semantic anchor groups, exact-phrase overconstraint, acronym disambiguation, and a deterministic natural-language score. One or two useful quoted phrases are allowed; three or more separately quoted concepts are treated as an overconstraint risk. `PSP` is considered disambiguated when the query includes the expanded pre-shipment-photo concept.

The generic AAA templates intentionally exclude page-specific brands, models, product IDs, filenames, image alt text, and anecdote entities. Model entities are permitted only for an explicitly model-specific query with a recorded rationale. The terminology research question explicitly asks for Reddit discussions; PSP/QC targets public buyer/forum discussion; provenance targets expert or editorial analysis.

Result screening classifies the actual URL independently from the requested lane. It then requires family-specific topic relevance. Official homepages, checkout/search pages, unrelated product pages, and news portals returned for a community query do not inherit the requested lane. Regional official hosts share one organization cluster and one independent evidence cluster.

Visual discovery distinguishes a resolved image locator from a page that may contain images. Provider image URLs, explicit media asset URLs, existing page image IDs, local paths, or source-specific asset IDs can qualify. A provider media label alone is written to `visual-page-candidates.csv`, never `image-source-candidates.csv`.
