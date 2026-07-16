# Research asset manifests

Future `new_page_build` work can inventory a prepared local folder before page architecture or targeted research:

```console
uv run reinaluxe-recovery research-build-asset-manifest \
  --asset-root data/research/assets/hermes/birkin/25 \
  --brand Hermes \
  --model Birkin \
  --size 25 \
  --output data/research/assets/hermes/birkin/25/manifest.csv
```

The command recursively inventories supported image and text files, leaves source files unchanged, writes stable relative paths, calculates SHA-256, and calculates an optional perceptual image hash when Pillow is available. Exact duplicates and practical perceptual duplicate candidates are recorded in `notes` without deleting or merging files.

Folder-derived categories are provisional until owner review. In particular, an `owner-original` folder produces a blank category plus a review note; `owner_original` becomes valid only when both owner review and owner-photography fields are explicitly true.

The CSV is owner-editable. Re-running the command preserves reviewed fields by relative path while refreshing inventory and hashes. `source_code` is internal provenance metadata and must not be copied into publication wording. Generated manifests plug directly into the Core-1A `new_page_build` asset-coverage and gap workflow.
