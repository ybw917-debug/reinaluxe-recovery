# Research visual candidates

Visual candidates are provider-returned image URLs or media metadata linked to a retained source page. Discovery does not download the image and does not require a visual-model API.

Each candidate records its source, category, brand/model configuration when known, proposed topic and section, returned caption or alt text, expected visual evidence, attribution requirement, duplicate status, publication permission, and owner-review status.

Supported source categories are:

- `existing_page_image`
- `owner_original`
- `owner_submitted`
- `qc_image`
- `seller_shot`
- `supplier_provided`
- `community_image`
- `official_reference`
- `expert_reference`
- `commercial_listing`
- `unknown_origin`

Provider discovery can classify public community, official, expert, and commercial references. It can never classify an image as `owner_original`. That category requires an explicit owner-reviewed record confirming owner photography. Visual appearance can support scoped observations about visible shape, proportion, stitching, structure, hardware, and comparison signals; it cannot prove origin, composition, authenticity, or universal factory consistency.
