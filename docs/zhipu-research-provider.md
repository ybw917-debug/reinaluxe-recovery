# Zhipu research provider

`ZhipuWebSearchProvider` is the first registered `ResearchSearchProvider`. Downstream contracts depend only on the provider interface, so future providers can be registered without modifying plans, source records, claims, snapshots, or exports.

Set these values outside Git:

```dotenv
ZHIPU_API_KEY=replace-locally
ZHIPU_SEARCH_ENGINE=replace-with-enabled-engine
ZHIPU_SUMMARIZER_MODEL=replace-with-enabled-glm-model
```

The provider validates all three before discovery. It implements `validate_configuration`, `capabilities`, `execute_query`, `normalize_results`, and `report_usage`. Usage reports include provider/model/engine labels and counts but never the API key. HTTP and response errors mention only stable query/source IDs and explicitly state that credentials were redacted.

The direct web-search request follows the documented 70-character query limit and uses `search_intent=false`, a result count of 10, `search_recency_filter=noLimit`, and `content_size=high`. The full temporal scope remains in the versioned query contract and source dates are screened downstream; unsupported custom date fields are not sent.

`--glm-assisted` invokes the optional `ZhipuGLMSourceAnalyzer` after deterministic source screening. Its prompt is confined to the screened record, requires atomic claims and limitations, and forbids adding URLs, image-authenticity conclusions, or private identities. Offline tests inject synthetic providers and never make live calls.
