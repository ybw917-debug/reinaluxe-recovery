"""Public deterministic offline batch-import boundary."""

from reinaluxe_recovery.batch.contracts import (
    BatchEntryResult,
    BatchEntryStatus,
    BatchFailureKind,
    BatchImportOptions,
    BatchImportResult,
    BatchManifest,
    BatchManifestEntry,
    BatchOverallStatus,
)
from reinaluxe_recovery.batch.exceptions import (
    BatchEntryFileError,
    BatchImportError,
    BatchManifestError,
    BatchPathError,
    BatchSelectionError,
    BatchSourceHashMismatchError,
)
from reinaluxe_recovery.batch.loader import (
    LoadedHtmlEntry,
    load_batch_manifest,
    load_html_entry,
    resolve_entry_path,
    validate_manifest_paths,
)
from reinaluxe_recovery.batch.reporting import build_batch_result
from reinaluxe_recovery.batch.workflow import BatchImportWorkflow

__all__ = [
    "BatchEntryFileError",
    "BatchEntryResult",
    "BatchEntryStatus",
    "BatchFailureKind",
    "BatchImportError",
    "BatchImportOptions",
    "BatchImportResult",
    "BatchImportWorkflow",
    "BatchManifest",
    "BatchManifestEntry",
    "BatchManifestError",
    "BatchOverallStatus",
    "BatchPathError",
    "BatchSelectionError",
    "BatchSourceHashMismatchError",
    "LoadedHtmlEntry",
    "build_batch_result",
    "load_batch_manifest",
    "load_html_entry",
    "resolve_entry_path",
    "validate_manifest_paths",
]
