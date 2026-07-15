"""Sanitized errors for the offline community workflow."""


class CommunityWorkflowError(Exception):
    """Base controlled error safe to show at the CLI boundary."""


class CommunityManifestError(CommunityWorkflowError):
    """The manifest or one referenced record is invalid."""


class CommunityPathError(CommunityWorkflowError):
    """A local input path violates confinement policy."""


class CommunityDecisionError(CommunityWorkflowError):
    """Review decisions are invalid or conflict."""
