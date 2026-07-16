# Research content production modes

Stage 009C-Core-1A adds a production intent to the existing provider-neutral research plan. It does not publish or modify an article. The intent controls which deterministic planning and synthesis artifacts are generated.

## Research only

`research_only` preserves the Stage 009C-Core behavior. It produces research, claims, evidence links, contradictions, opportunities, and the five shared editorial-synthesis registers without a page package.

## Legacy reconstruction

`legacy_reconstruction` reads the current normalized article in immutable mode and defaults to preserving existing images and distinctive material, requiring no new owner-handled evidence, allowing no more than three new sections, and selecting `highly_assertive_but_supportable` wording when the evidence permits it.

The change strategy is KEEP/ENRICH first. Existing section IDs, research questions, sources, images, observations, inferences, wording, limitations, and operations stay linked. A planning-only run maps the page without drafting or live search; an analyzed run adds source-backed enrichment candidates. DELETE is never inferred merely because a section is long or lightly evidenced.

## New page build

`new_page_build` inspects reusable topic knowledge and a confined local asset manifest before identifying new evidence needs. It records assets with SHA-256 hashes without changing them, separates text and image gaps, and creates a new evidence-led blueprint rather than inheriting an old page structure. First-party physical evidence can strengthen a future page but is not a prerequisite.

Run either planning mode offline with `research-plan`. The selected mode-specific package is written beside `research-plan.json` and `query-plan.csv`.
