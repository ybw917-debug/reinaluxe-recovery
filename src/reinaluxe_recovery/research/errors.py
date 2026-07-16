"""Controlled errors for research orchestration."""


class ResearchError(Exception):
    """Base error for deterministic research workflows."""


class ResearchConfigurationError(ResearchError):
    """Provider or request configuration is unusable."""


class ResearchArtifactError(ResearchError):
    """A research input or output artifact is invalid."""
