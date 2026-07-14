"""Controlled audit failures."""


class AuditError(RuntimeError):
    """Base audit-system error."""


class NoMatchingArticlesError(AuditError):
    """No persisted Article versions matched the requested selection."""
