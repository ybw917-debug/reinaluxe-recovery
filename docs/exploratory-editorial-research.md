# Exploratory editorial research

Stage 009C-Core-2 makes `exploratory_editorial_research` the default research mode when a legacy reconstruction request omits `mode`. It complements strict claim verification: broad discovery and market synthesis can continue when a source is anecdotal, commercial, seller-authored, old, single-source, or classified outside the requested lane, while direct factual claims still require direct support.

The AAA query universe contains twelve families and three variants per family. It mixes direct, colloquial, synonym, problem-oriented, comparison, buyer-experience, commercial-language, and adjacent-domain formulations in English and Chinese. The default pilot selects at most twelve first-round queries. GLM then proposes one bounded second-round plan of at most eight queries, with source IDs, theme, rationale, expected information gain, target provider, and target lane. A third round is never automatic.

Provider strategy is asymmetric by design:

- Brave handles Reddit, forums, broad English discovery, and English adjacent-domain searches.
- Zhipu handles Chinese discovery and selected general-web searches.
- GLM performs expansion, source understanding, theme extraction, pattern synthesis, contradiction mapping, adjacent-domain connection, buyer guidance, publication-module generation, and overclaim review.

Each retained source receives separate utility scores for relevance, novelty, buyer language, terminology, visual value, patterns, contradictions, query expansion, publication value, and factual reliability. Low factual reliability does not erase market-language or expansion value. Records also state commercial and independence risk, allowed editorial uses, and prohibited factual uses.

Run the bounded pilot:

```console
uv run reinaluxe-recovery research-explore \
  --request docs/examples/aaa-pillar-001.yaml \
  --output data/research/exploratory/aaa-pillar-001-core2 \
  --first-round-calls 12 \
  --second-round-calls 8
```

The workflow never crawls result pages, requests Reddit outside the selected provider, downloads images, modifies WordPress or article content, writes production SQLite, retries a failed web query, or starts an automatic third round. It produces planning-only modules and a change manifest.

Required editorial artifacts include:

- `research-landscape.md`;
- `discovered-theme-register.csv`;
- `market-pattern-register.csv`;
- `editorial-inference-register.csv`;
- `buyer-guidance-register.csv`;
- `contradiction-map.csv`;
- `adjacent-domain-connections.csv`;
- `follow-up-query-plan.csv`;
- `section-enrichment-copy.md`;
- `image-analysis-opportunities.csv`;
- `publication-modules.md`;
- `content-change-manifest.csv`;
- `overclaim-review.csv`.

Publication modules are source-linked, substantial, and publication-oriented. The final deterministic review rejects generated URLs, invented owner or customer experience, precise unsupported measurements, factory visits, tannery confirmation, and counterfeit purchasing assistance before any module reaches the Markdown outputs.
