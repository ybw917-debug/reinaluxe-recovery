# Research smoke testing

`research-smoke` validates real provider discovery with one to three selected query families. It is a coverage test, not the full AAA pilot.

```console
uv run reinaluxe-recovery research-smoke \
  --request docs/examples/aaa-pillar-001.yaml \
  --query-families terminology,psp_qc,handmade_provenance \
  --output data/research/smoke/aaa-pillar-001-brave-v1 \
  --research-database data/research/runtime/research.sqlite \
  --glm-assisted
```

The command makes no more than three Web Search calls, requests no more than ten results per call, processes no more than thirty provider results, and retains no more than twenty sources. It has no fallback or retry path. A failure in one query does not retry that query and does not prevent the other independently planned calls. Returned pages are not fetched, Reddit is not requested directly, browser automation is not used, and provider-discovered images are not downloaded.

Every provider result remains linked to its provider identifier, query, family, retrieval time, lane, and access classification. Every requested lane must match deterministic URL, domain, content, or provider-image metadata signals; a planned lane is not used to disguise a natural provider shortfall. Malformed URLs, invalid Reddit locations, PSP gaming results, corrupted content, commercial material presented as editorial, exact URL duplicates, and identical title/snippet duplicates are reported. Relevance is conjunctive: replica-bag context and all family-specific evidence groups must pass. A failed coverage target is recorded rather than fabricated.

Run the [query-integrity preview](research-query-integrity.md) first. The smoke call register preserves the exact search query, requested lane, domain filter, maximum results, anchors, and exclusions. Query-quality failures make no provider call. Results record requested and classified lanes separately, and family-specific lexical relevance is required before retention.

Paid discovery requires both structural query quality and retrieval quality. A lane-contradictory research question, over-quoted query, unmitigated ambiguous acronym, incomplete semantic anchor groups, or low natural-language score stops before the provider call. GLM analysis receives only retained sources. Fewer than three retained sources stops before GLM-assisted cross-source synthesis and records `provider_coverage_insufficient`.

Compare the Brave run with an existing Zhipu v2 register without another provider call:

```console
uv run reinaluxe-recovery research-compare-providers \
  --request docs/examples/aaa-pillar-001.yaml \
  --query-families terminology,psp_qc,handmade_provenance \
  --brave-run data/research/smoke/aaa-pillar-001-brave-v1 \
  --zhipu-run data/research/smoke/aaa-pillar-001-zhipu-after-df18bbb \
  --output data/research/smoke/aaa-pillar-001-brave-v1
```

The final recommendation is one of `full_run_recommended`, `full_run_recommended_with_adjustments`, `provider_coverage_insufficient`, `configuration_failed`, or `analysis_failed`. Runtime output under `data/research/smoke/` is ignored by Git.
