# Brave research providers and lane routing

Stage 009C-Core-1C adds `BraveWebSearchProvider`, a non-executing `BraveImageSearchProvider` contract, and `LaneRoutedSearchProvider`. Set `BRAVE_SEARCH_API_KEY` outside Git. The existing Zhipu web-search and GLM analysis providers remain available.

The default `lane-routed` provider uses this fixed table:

| Source lane | Provider |
|---|---|
| `community_reddit` | `brave-web-search` |
| `community_forums` | `brave-web-search` |
| `expert_editorial` | `brave-web-search` |
| `primary_official` | `zhipu-web-search` |
| `visual_image` | `brave-image-search` |
| `commercial_observation` | configurable |

Set `RESEARCH_COMMERCIAL_SEARCH_PROVIDER` to `brave-web-search` (the default) or `zhipu-web-search`. Routing selects exactly one provider and has no retry or fallback path.

Brave Web Search uses the exact validated query and a maximum count of ten. It only normalizes provider-returned title, URL, description, date, language, and profile metadata. It never requests a result page. The image provider exposes configuration, capability, normalization, and usage contracts, but live image execution is disabled in this stage and no image is downloaded.

Provider comparison is offline. `research-compare-providers` reclassifies both raw result registers with the current deterministic rules and writes `provider-comparison-report.md` plus `provider-comparison-register.csv`. In particular, the Zhipu v2 input is not queried or analyzed again.
