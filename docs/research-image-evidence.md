# Research image evidence

Visual discovery is a first-class part of a search run. Provider-returned image URLs and metadata are registered with their source page, originating query, alt text, caption, optional brand/model/topic scope, claim links, permission status, and owner-review status. Exact normalized image URLs are deduplicated.

Stage 009C-Core does not download, publish, or visually authenticate an image. Every image starts with unknown publication permission and pending owner review. Every image-evidence record explicitly states that appearance is not proof of provenance or authenticity. Private supplier identities remain excluded. A future `VisualAnalysisProvider` interface exists, but no visual-model credential is required.

Use `research-image-review` to create `image-review.csv` and a safeguard summary. An owner must separately establish permission and editorial suitability before any later content workflow can use an image.
