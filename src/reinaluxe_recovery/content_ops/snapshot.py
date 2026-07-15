"""Deterministic approved-knowledge snapshot construction."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from reinaluxe_recovery.community.io import prepare_output, write_json, write_jsonl
from reinaluxe_recovery.community.normalization import (
    content_hash,
    normalize_datetime,
    stable_id,
)
from reinaluxe_recovery.content_ops.common import (
    file_sha256,
    model_payload,
    typed_jsonl,
)
from reinaluxe_recovery.content_ops.errors import SnapshotError
from reinaluxe_recovery.domain.community import (
    ApprovedKnowledgeEntry,
    KnowledgePublicationStatus,
)
from reinaluxe_recovery.domain.content_ops import KnowledgeSnapshotManifest


def build_knowledge_snapshot(
    inputs: list[Path], output: Path
) -> KnowledgeSnapshotManifest:
    """Build one immutable snapshot from one or more Stage 009A KB batches."""
    if not inputs:
        raise SnapshotError("at least one approved knowledge input is required")
    batch_ids = sorted(path.resolve().name for path in inputs)
    if len(batch_ids) != len(set(batch_ids)):
        raise SnapshotError("knowledge input batch directory names must be unique")
    source_hashes: dict[str, str] = {}
    by_id: dict[str, ApprovedKnowledgeEntry] = {}
    for input_path in sorted(inputs, key=lambda item: item.resolve().name):
        source = input_path / "approved-knowledge.jsonl"
        batch_id = input_path.resolve().name
        source_hashes[batch_id] = file_sha256(source)
        for entry in typed_jsonl(source, ApprovedKnowledgeEntry):
            existing = by_id.get(entry.knowledge_entry_id)
            if existing is not None and model_payload(existing) != model_payload(entry):
                raise SnapshotError(
                    f"knowledge_entry_id has conflicting content: {entry.knowledge_entry_id}"
                )
            by_id[entry.knowledge_entry_id] = entry
    if not by_id:
        raise SnapshotError("approved knowledge inputs contain no entries")

    created_at = max(entry.reviewed_at for entry in by_id.values())
    publishable: list[ApprovedKnowledgeEntry] = []
    internal: list[ApprovedKnowledgeEntry] = []
    excluded: list[dict[str, Any]] = []
    for entry in sorted(by_id.values(), key=lambda item: item.knowledge_entry_id):
        reasons: list[str] = []
        if entry.stale_after is not None and entry.stale_after <= created_at:
            reasons.append("stale")
        if entry.contradicted_by_entry_ids:
            reasons.append("contradicted")
        if entry.publication_status in {
            KnowledgePublicationStatus.PENDING,
            KnowledgePublicationStatus.DO_NOT_PUBLISH,
        }:
            reasons.append(f"publication_status:{entry.publication_status.value}")
        if reasons:
            excluded.append(
                {"knowledge_entry_id": entry.knowledge_entry_id, "reasons": reasons}
            )
        elif entry.publication_status is KnowledgePublicationStatus.INTERNAL_ONLY:
            internal.append(entry)
        else:
            publishable.append(entry)

    included = sorted(
        [*publishable, *internal], key=lambda item: item.knowledge_entry_id
    )
    base = {
        "schema_version": "1.0",
        "created_at": created_at,
        "source_batch_ids": batch_ids,
        "knowledge_entry_ids": [item.knowledge_entry_id for item in included],
        "entry_count": len(included),
        "approved_count": sum(not item.required_qualification for item in publishable),
        "qualified_count": sum(
            bool(item.required_qualification) for item in publishable
        ),
        "internal_only_count": len(internal),
        "excluded_entry_ids": sorted(item["knowledge_entry_id"] for item in excluded),
        "source_hashes": dict(sorted(source_hashes.items())),
    }
    identity = {
        **base,
        "created_at": normalize_datetime(created_at),
    }
    snapshot_material = {
        "manifest": identity,
        "publishable_entries": [model_payload(item) for item in publishable],
        "internal_entries": [model_payload(item) for item in internal],
    }
    snapshot_hash = content_hash(snapshot_material)
    manifest = KnowledgeSnapshotManifest.model_validate(
        {
            **base,
            "snapshot_id": stable_id("ksnap", snapshot_material),
            "snapshot_hash": snapshot_hash,
        }
    )
    prepare_output(output)
    write_json(output / "knowledge-snapshot-manifest.json", model_payload(manifest))
    write_jsonl(output / "approved-knowledge-snapshot.jsonl", publishable)
    write_jsonl(
        output / "qualified-knowledge-snapshot.jsonl",
        [item for item in publishable if item.required_qualification],
    )
    write_jsonl(output / "internal-only-index.jsonl", internal)
    write_json(output / "excluded-knowledge.json", excluded)
    write_json(
        output / "snapshot-summary.json",
        {
            "schema_version": "1.0",
            "snapshot_id": manifest.snapshot_id,
            "publishable_count": len(publishable),
            "qualified_count": manifest.qualified_count,
            "internal_only_count": len(internal),
            "excluded_count": len(excluded),
            "restricted_provenance_exported": False,
        },
    )
    return manifest


def validate_snapshot(directory: Path) -> KnowledgeSnapshotManifest:
    """Validate the manifest hash and exact snapshot membership."""
    from reinaluxe_recovery.content_ops.common import typed_json  # avoid cycle

    manifest = typed_json(
        directory / "knowledge-snapshot-manifest.json", KnowledgeSnapshotManifest
    )
    publishable = typed_jsonl(
        directory / "approved-knowledge-snapshot.jsonl", ApprovedKnowledgeEntry
    )
    internal = typed_jsonl(
        directory / "internal-only-index.jsonl", ApprovedKnowledgeEntry
    )
    payload = manifest.model_dump(mode="json", exclude={"snapshot_id", "snapshot_hash"})
    snapshot_material = {
        "manifest": payload,
        "publishable_entries": [model_payload(item) for item in publishable],
        "internal_entries": [model_payload(item) for item in internal],
    }
    if content_hash(snapshot_material) != manifest.snapshot_hash:
        raise SnapshotError("knowledge snapshot manifest hash mismatch")
    ids = sorted(item.knowledge_entry_id for item in [*publishable, *internal])
    if ids != manifest.knowledge_entry_ids:
        raise SnapshotError("knowledge snapshot membership does not match manifest")
    if any(
        item.publication_status is KnowledgePublicationStatus.INTERNAL_ONLY
        for item in publishable
    ):
        raise SnapshotError("publishable snapshot contains internal-only knowledge")
    return manifest
