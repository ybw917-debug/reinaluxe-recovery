"""Expected errors for deterministic local batch imports."""


class BatchImportError(Exception):
    """Base error for the local batch boundary."""


class BatchManifestError(BatchImportError, ValueError):
    """Raised when a manifest cannot be read or validated."""


class BatchPathError(BatchManifestError):
    """Raised when an entry path violates the manifest-root policy."""


class BatchSelectionError(BatchImportError, ValueError):
    """Raised when requested filters select no enabled entries."""


class BatchEntryFileError(BatchImportError, OSError):
    """Raised when one selected local HTML file cannot be safely loaded."""


class BatchSourceHashMismatchError(BatchEntryFileError):
    """Raised before parsing when an expected source hash does not match."""
