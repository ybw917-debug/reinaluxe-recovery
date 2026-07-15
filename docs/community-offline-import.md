# Community Offline Import

## Command

```powershell
uv run reinaluxe-recovery community-import `
  --manifest data\community-intelligence\inbox\batch-001\manifest.json `
  --output data\community-intelligence\imports\batch-001
```

The importer reads only the manifest and confined relative files. Absolute
paths and traversal outside the manifest directory are rejected. A URL is
audit metadata and is never fetched. Files require an explicit encoding, or
inherit the manifest's explicit `default_encoding`.

## Recommended pilot manifest

Use explicit human-readable IDs in a small owner-reviewed pilot so claims can
reference sources before import:

```json
{
  "schema_version": "1.0",
  "import_batch_id": "pilot-001",
  "created_at": "2026-07-15T10:00:00+08:00",
  "default_encoding": "utf-8",
  "metadata": {"purpose": "sanitized Stage 009B pilot"},
  "sources": [
    {
      "source_record_id": "pilot-source-001",
      "platform": "owner",
      "community_or_channel": "offline pilot",
      "source_type": "owner_note",
      "retrieved_at": "2026-07-15T10:00:00+08:00",
      "language": "en",
      "input_file": "excerpts/source-001.txt",
      "input_format": "text",
      "encoding": "utf-8",
      "source_scope": "one named model and variant",
      "copyright_retention_mode": "necessary_excerpt_only",
      "visibility": "internal_only",
      "metadata": {}
    }
  ],
  "candidate_claims": [
    {
      "claim_id": "pilot-claim-001",
      "claim_text": "One atomic, qualified proposition.",
      "claim_type": "other",
      "model": "Example model",
      "source_record_ids": ["pilot-source-001"],
      "evidence_record_ids": [],
      "extraction_method": "manual",
      "sensitivity": "internal",
      "proposed_publication_scope": "internal_only"
    }
  ],
  "evidence_records": []
}
```

A JSON file reference may contain one object or a list of objects. Inline
fields override fields in that local JSON file. Text references are source
excerpts only. Unknown fields, invalid enums, naive timestamps, mismatched
supplied content hashes, and dangling IDs fail before output is written.

Outputs are normalized source, claim, and evidence JSONL files plus warnings
and a stable summary. Rerunning identical input produces byte-identical output.
Exact duplicates are reported; likely duplicates remain distinct and appear in
review.
