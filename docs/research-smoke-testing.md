# Research smoke testing

`research-smoke` validates real provider discovery with one to three selected query families. It is a coverage test, not the full AAA pilot.

```console
uv run reinaluxe-recovery research-smoke \
  --request docs/examples/aaa-pillar-001.yaml \
  --query-families terminology,psp_qc,handmade_provenance \
  --output data/research/smoke/aaa-pillar-001-zhipu \
  --research-database data/research/runtime/research.sqlite \
  --glm-assisted
```

The command makes no more than three Web Search calls, requests no more than fifteen results per call, processes no more than forty-five provider results, and retains no more than twenty sources. It has no fallback or retry path. Returned pages are not fetched, Reddit is not requested directly, browser automation is not used, and provider-discovered images are not downloaded.

Every provider result remains linked to its provider identifier, query, family, retrieval time, lane, and access classification. Reddit, public-forum, and official lanes require matching URL or brand-domain signals; a planned lane is not used to disguise a natural provider shortfall. Malformed URLs, invalid Reddit locations, exact URL duplicates, and identical title/snippet duplicates are reported. A failed coverage target is recorded rather than fabricated.

The final recommendation is one of `full_run_recommended`, `full_run_recommended_with_adjustments`, `provider_coverage_insufficient`, `configuration_failed`, or `analysis_failed`. Runtime output under `data/research/smoke/` is ignored by Git.
