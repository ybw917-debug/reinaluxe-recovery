"""Provider boundaries independent of research contracts and workflows."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any

from reinaluxe_recovery.research.contracts import ResearchQuery


class ResearchSearchProvider(ABC):
    """Search-provider interface used by discovery orchestration."""

    provider_name: str

    @abstractmethod
    def validate_configuration(self) -> None:
        """Raise a controlled error when required configuration is missing."""

    @abstractmethod
    def capabilities(self) -> Mapping[str, Any]:
        """Describe provider features without exposing configuration secrets."""

    @abstractmethod
    def execute_query(self, query: ResearchQuery) -> Any:
        """Execute one planned query and return the provider response."""

    @abstractmethod
    def normalize_results(
        self, query: ResearchQuery, response: Any
    ) -> list[dict[str, Any]]:
        """Normalize an actual response into provider-neutral result dictionaries."""

    @abstractmethod
    def report_usage(self) -> Mapping[str, Any]:
        """Return non-secret deterministic usage counters."""


class VisualAnalysisProvider(ABC):
    """Optional future boundary; Stage 009C-Core does not require an implementation."""

    @abstractmethod
    def analyze_images(self, image_urls: list[str]) -> list[dict[str, Any]]:
        """Analyze owner-approved public images without establishing provenance."""
