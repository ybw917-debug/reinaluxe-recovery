# Zhipu research provider

`ZhipuWebSearchProvider` remains a registered `ResearchSearchProvider` and supplies the `primary_official` lane in the default [lane router](brave-research-provider.md). Downstream contracts still depend only on the provider interface.

Set these values outside Git:

```dotenv
ZHIPU_API_KEY=replace-locally
ZHIPU_SEARCH_ENGINE=replace-with-enabled-engine
ZHIPU_SUMMARIZER_MODEL=replace-with-enabled-glm-model
```

The provider validates all three before discovery. It implements `validate_configuration`, `capabilities`, `execute_query`, `normalize_results`, and `report_usage`. Usage reports include provider/model/engine labels and counts but never the API key. HTTP and response errors mention only stable query/source IDs and explicitly state that credentials were redacted.

The direct web-search request sends the exact quality-approved query without silent truncation and uses `search_intent=false`, a result count of 10 by default (never more than 15), `search_recency_filter=noLimit`, and `content_size=high`. A Reddit-targeted query also supplies `search_domain_filter=reddit.com`. The full temporal scope remains in the versioned query contract and source dates are screened downstream; unsupported custom date fields are not sent.

`--glm-assisted` invokes the optional `ZhipuGLMSourceAnalyzer` after deterministic source screening. Its prompt is confined to the screened record, requires atomic claims and limitations, and forbids adding URLs, image-authenticity conclusions, or private identities. Offline tests inject synthetic providers and never make live calls.

`research-smoke` is the bounded live validation path. It preserves provider result identifiers, returned content/media, retrieval timestamps, and query traceability. The analyzer cannot create source URLs, and claims containing model-added URLs or numeric values absent from the provider-returned source record are rejected. No result page is fetched and no automatic provider fallback or retry is configured.
