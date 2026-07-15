"""Controlled errors for offline content opportunity planning."""


class ContentOpsError(Exception):
    """A sanitized validation or workflow error safe for CLI display."""


class SnapshotError(ContentOpsError):
    pass


class PageContextError(ContentOpsError):
    pass


class OpportunityError(ContentOpsError):
    pass


class OpportunityDecisionError(ContentOpsError):
    pass


class ChangeManifestError(ContentOpsError):
    pass
