# Article-driven multi-source research

Stage 009C-Core turns an existing repository article version or an owner-defined topic into a deterministic research plan, screened public-source register, atomic claims, evidence relationships, contradictions, visual candidates, reusable topic opportunities, and a compact owner review package. It does not draft or publish copy and has no WordPress write path.

## Modes and stages

The request contracts support `article_research`, `topic_build`, `topic_refresh`, `claim_verify`, `evidence_gap_fill`, and `visual_research`. Article mode reads normalized JSON, owner-provided HTML, or the existing SQLite article version in immutable read-only mode. It extracts title, H1, headings, claim-like statements, images, internal links, first-hand language, evidence-pending claims, missing questions, and lane-specific gaps. It never mechanically recommends shortening.

The CLI stages are intentionally separable:

```console
uv run reinaluxe-recovery research-plan --request docs/examples/aaa-pillar-001.yaml --output data/research/plans/aaa-pillar-001
uv run reinaluxe-recovery research-discover --plan data/research/plans/aaa-pillar-001 --output data/research/runs/aaa-pillar-001
uv run reinaluxe-recovery research-analyze --run data/research/runs/aaa-pillar-001 --output data/research/analysis/aaa-pillar-001 --glm-assisted
uv run reinaluxe-recovery research-build-snapshot --analysis data/research/analysis/aaa-pillar-001 --output data/research/analysis/aaa-pillar-001
uv run reinaluxe-recovery research-export-review --analysis data/research/analysis/aaa-pillar-001 --output data/research/reviews/aaa-pillar-001
```

`research-refresh` executes the same bounded stages into subdirectories. `research-image-review` exports metadata and blank review fields without downloading images.

## Determinism and traceability

Requests, plans, runs, and snapshots use canonical SHA-256 hashes. IDs derive from normalized scope rather than wall-clock time. Every accepted source retains its query ID and actual provider-returned URL; every claim has at least one source/evidence link. Repeated URLs are excluded before analysis. An analyzer cannot create a new source candidate.

The committed AAA file is a JSON-formatted YAML 1.2 template, allowing the core loader to work without another required dependency. Conventional YAML is accepted when PyYAML is available.
