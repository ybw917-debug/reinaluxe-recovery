"""Lane-based research provider routing without fallback or retries."""

from __future__ import annotations

import os
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from reinaluxe_recovery.research.contracts import ResearchQuery, SourceLane
from reinaluxe_recovery.research.errors import ResearchConfigurationError, ResearchError
from reinaluxe_recovery.research.providers.base import ResearchSearchProvider
from reinaluxe_recovery.research.providers.brave import (
    BraveImageSearchProvider,
    BraveWebSearchProvider,
)
from reinaluxe_recovery.research.providers.zhipu import ZhipuWebSearchProvider


@dataclass(frozen=True)
class RoutedProviderResponse:
    provider: ResearchSearchProvider
    value: Any


class LaneRoutedSearchProvider(ResearchSearchProvider):
    """Route each query to exactly one configured provider by requested lane."""

    provider_name = "lane-routed"

    def __init__(
        self,
        routes: Mapping[SourceLane, ResearchSearchProvider],
    ) -> None:
        missing = set(SourceLane) - set(routes)
        if missing:
            names = ", ".join(sorted(item.value for item in missing))
            raise ResearchConfigurationError(f"provider routes missing lanes: {names}")
        self._routes = dict(routes)
        self._lane_calls: Counter[SourceLane] = Counter()

    def provider_for(self, lane: SourceLane) -> ResearchSearchProvider:
        return self._routes[lane]

    def validate_configuration(self) -> None:
        validated: set[int] = set()
        for provider in self._routes.values():
            identity = id(provider)
            if identity in validated:
                continue
            provider.validate_configuration()
            validated.add(identity)

    def capabilities(self) -> Mapping[str, Any]:
        return {
            "provider": self.provider_name,
            "lane_routing": True,
            "automatic_fallback": False,
            "retry_count": 0,
            "requested_result_count": min(
                int(provider.capabilities().get("requested_result_count", 10))
                for provider in self._routes.values()
            ),
            "routes": {
                lane.value: provider.provider_name
                for lane, provider in sorted(
                    self._routes.items(), key=lambda item: item[0].value
                )
            },
        }

    def execute_query(self, query: ResearchQuery) -> RoutedProviderResponse:
        provider = self.provider_for(query.requested_source_lane)
        value = provider.execute_query(query)
        self._lane_calls[query.requested_source_lane] += 1
        return RoutedProviderResponse(provider=provider, value=value)

    def normalize_results(
        self, query: ResearchQuery, response: Any
    ) -> list[dict[str, Any]]:
        if not isinstance(response, RoutedProviderResponse):
            raise ResearchError(
                f"missing routed provider response for {query.query_id}"
            )
        results = response.provider.normalize_results(query, response.value)
        return [
            {**item, "provider": response.provider.provider_name} for item in results
        ]

    def report_usage(self) -> Mapping[str, Any]:
        unique = {
            provider.provider_name: provider for provider in self._routes.values()
        }
        return {
            "provider": self.provider_name,
            "lane_calls": {
                lane.value: self._lane_calls[lane]
                for lane in sorted(SourceLane, key=lambda item: item.value)
            },
            "provider_usage": {
                name: dict(provider.report_usage())
                for name, provider in sorted(unique.items())
            },
            "automatic_fallback": False,
            "retry_count": 0,
            "credentials_serialized": False,
        }


def default_lane_routed_provider(
    *, environ: Mapping[str, str] | None = None
) -> LaneRoutedSearchProvider:
    """Build the Stage 009C-Core-1C routing table."""
    values = os.environ if environ is None else environ
    brave_web = BraveWebSearchProvider(environ=values, result_count=10)
    brave_image = BraveImageSearchProvider(environ=values, result_count=10)
    zhipu = ZhipuWebSearchProvider(environ=values, result_count=10)
    commercial_name = (
        values.get("RESEARCH_COMMERCIAL_SEARCH_PROVIDER", "brave-web-search")
        .strip()
        .casefold()
    )
    commercial = {
        "brave": brave_web,
        "brave-web-search": brave_web,
        "zhipu": zhipu,
        "zhipu-web-search": zhipu,
    }.get(commercial_name)
    if commercial is None:
        raise ResearchConfigurationError(
            "RESEARCH_COMMERCIAL_SEARCH_PROVIDER must be brave-web-search or "
            "zhipu-web-search"
        )
    return LaneRoutedSearchProvider(
        {
            SourceLane.COMMUNITY_REDDIT: brave_web,
            SourceLane.COMMUNITY_FORUMS: brave_web,
            SourceLane.EXPERT_EDITORIAL: brave_web,
            SourceLane.PRIMARY_OFFICIAL: zhipu,
            SourceLane.VISUAL_IMAGE: brave_image,
            SourceLane.COMMERCIAL_OBSERVATION: commercial,
        }
    )
