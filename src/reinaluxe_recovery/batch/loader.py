"""Local JSON manifest and HTML loading with manifest-root confinement."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from reinaluxe_recovery.batch.contracts import BatchManifest, BatchManifestEntry
from reinaluxe_recovery.batch.exceptions import (
    BatchEntryFileError,
    BatchManifestError,
    BatchPathError,
    BatchSourceHashMismatchError,
)
from reinaluxe_recovery.importing import hash_html_body


@dataclass(frozen=True, slots=True)
class LoadedHtmlEntry:
    """One safely resolved and decoded local HTML file."""

    path: Path
    html_body: str
    source_hash: str


def load_batch_manifest(path: Path) -> BatchManifest:
    """Read and strictly validate one local UTF-8 JSON manifest."""
    resolved = path.expanduser().resolve()
    try:
        raw = resolved.read_bytes()
    except OSError as error:
        raise BatchManifestError(
            f"could not read manifest {resolved}: {error}"
        ) from error
    try:
        return BatchManifest.model_validate_json(raw)
    except ValidationError as error:
        raise BatchManifestError(
            f"invalid batch manifest {resolved}: {error}"
        ) from error


def resolve_entry_path(
    manifest_path: Path,
    entry: BatchManifestEntry,
) -> Path:
    """Resolve a relative entry path and confine it to the manifest directory."""
    if entry.html_path.is_absolute():
        raise BatchPathError(
            f"entry {entry.entry_id!r} uses an absolute html_path; only paths "
            "relative to the manifest directory are allowed"
        )
    try:
        root = manifest_path.expanduser().resolve().parent
        resolved = (root / entry.html_path).resolve()
    except OSError as error:
        raise BatchPathError(
            f"entry {entry.entry_id!r} html_path could not be resolved: "
            f"{entry.html_path}: {error}"
        ) from error
    if not resolved.is_relative_to(root):
        raise BatchPathError(
            f"entry {entry.entry_id!r} html_path escapes the manifest directory: "
            f"{entry.html_path}"
        )
    return resolved


def validate_manifest_paths(manifest_path: Path, manifest: BatchManifest) -> None:
    """Reject every absolute or escaping path before lifecycle or entry work."""
    resolved_paths: set[str] = set()
    for entry in manifest.entries:
        resolved = resolve_entry_path(manifest_path, entry)
        path_key = str(resolved).casefold()
        if path_key in resolved_paths:
            raise BatchPathError(
                f"entries resolve to the same html_path: {entry.html_path}"
            )
        resolved_paths.add(path_key)


def load_html_entry(
    manifest_path: Path,
    entry: BatchManifestEntry,
) -> LoadedHtmlEntry:
    """Read, decode, and optionally hash-check one entry before parsing."""
    resolved = resolve_entry_path(manifest_path, entry)
    try:
        raw = resolved.read_bytes()
    except OSError as error:
        raise BatchEntryFileError(
            f"could not read HTML for entry {entry.entry_id!r} at {resolved}: {error}"
        ) from error
    try:
        html_body = raw.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise BatchEntryFileError(
            f"HTML for entry {entry.entry_id!r} is not valid UTF-8: {resolved}"
        ) from error
    source_hash = hash_html_body(html_body)
    if (
        entry.expected_source_hash is not None
        and source_hash != entry.expected_source_hash
    ):
        raise BatchSourceHashMismatchError(
            f"source hash mismatch for entry {entry.entry_id!r}: expected "
            f"{entry.expected_source_hash}, got {source_hash}"
        )
    return LoadedHtmlEntry(
        path=resolved,
        html_body=html_body,
        source_hash=source_hash,
    )
