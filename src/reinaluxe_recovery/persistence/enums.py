"""Stable string values stored by the persistence schema."""

from enum import StrEnum


class StoredImportStatus(StrEnum):
    """Import outcome preserved on a crawl record."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"


class StoredWarningSeverity(StrEnum):
    """Diagnostic severity preserved with an import warning."""

    WARNING = "warning"
    FATAL = "fatal"
