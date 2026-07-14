"""Confined atomic snapshot and compatible manifest generation."""

import os
from pathlib import Path

from reinaluxe_recovery.acquisition.contracts import (
    AcquiredPage,
    AcquisitionRequest,
    AcquisitionStatus,
)
from reinaluxe_recovery.acquisition.exceptions import SnapshotError
from reinaluxe_recovery.batch.contracts import BatchManifest, BatchManifestEntry
from reinaluxe_recovery.importing import hash_html_body


def confined_path(root: Path, relative: Path) -> Path:
    if relative.is_absolute() or ".." in relative.parts:
        raise SnapshotError("output path must be relative and cannot traverse")
    resolved_root = root.resolve()
    resolved = (resolved_root / relative).resolve()
    if not resolved.is_relative_to(resolved_root):
        raise SnapshotError("output path escapes the acquisition directory")
    return resolved


def atomic_write(path: Path, data: bytes, *, overwrite: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        raise SnapshotError(f"refusing to overwrite existing file: {path}")
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_bytes(data)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def source_hash(body: bytes) -> str:
    try:
        return hash_html_body(body.decode("utf-8-sig"))
    except UnicodeDecodeError as error:
        raise SnapshotError("HTML snapshot is not valid UTF-8") from error


def snapshot_relative_path(entry_id: str) -> Path:
    return Path("html") / f"{entry_id}.html"


def persist_page(
    root: Path, page: AcquiredPage, body: bytes, *, overwrite: bool
) -> AcquiredPage:
    digest = source_hash(body)
    relative = snapshot_relative_path(page.entry_id)
    target = confined_path(root, relative)
    metadata_path = confined_path(root, Path("metadata") / f"{page.entry_id}.json")
    if target.exists() and source_hash(target.read_bytes()) == digest:
        return page.model_copy(
            update={
                "source_hash": digest,
                "snapshot_path": relative,
                "status": AcquisitionStatus.UNCHANGED,
            }
        )
    atomic_write(target, body, overwrite=overwrite)
    updated = page.model_copy(update={"source_hash": digest, "snapshot_path": relative})
    atomic_write(
        metadata_path,
        f"{updated.model_dump_json(indent=2)}\n".encode(),
        overwrite=overwrite,
    )
    return updated


def build_manifest(
    request: AcquisitionRequest, pages: list[AcquiredPage]
) -> BatchManifest:
    entries = [
        BatchManifestEntry(
            entry_id=p.entry_id,
            html_path=p.snapshot_path,
            source_url=p.final_url or p.requested_url,
            fetched_at=p.fetched_at,
            status_code=p.status_code or 200,
            headers=p.response_headers,
            expected_source_hash=p.source_hash,
        )
        for p in pages
        if p.status in {AcquisitionStatus.FETCHED, AcquisitionStatus.UNCHANGED}
        and p.snapshot_path is not None
        and p.fetched_at is not None
    ]
    return BatchManifest(
        contract_version="1.0",
        batch_id=f"acquisition-{request.acquisition_id}",
        created_at=request.created_at,
        entries=entries,
        metadata={"acquisition_id": request.acquisition_id},
    )


def write_manifest(root: Path, manifest: BatchManifest, *, overwrite: bool) -> Path:
    path = confined_path(root, Path("manifest.json"))
    atomic_write(
        path, f"{manifest.model_dump_json(indent=2)}\n".encode(), overwrite=overwrite
    )
    return path
