"""Provider registry allowing additions without downstream contract changes."""

from __future__ import annotations

from collections.abc import Callable

from reinaluxe_recovery.research.errors import ResearchConfigurationError
from reinaluxe_recovery.research.providers.base import ResearchSearchProvider
from reinaluxe_recovery.research.providers.brave import (
    BraveImageSearchProvider,
    BraveWebSearchProvider,
)
from reinaluxe_recovery.research.providers.routing import default_lane_routed_provider
from reinaluxe_recovery.research.providers.zhipu import ZhipuWebSearchProvider

ProviderFactory = Callable[[], ResearchSearchProvider]


class ResearchProviderRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, ProviderFactory] = {}

    def register(self, name: str, factory: ProviderFactory) -> None:
        self._factories[name.strip().casefold()] = factory

    def create(self, name: str) -> ResearchSearchProvider:
        key = name.strip().casefold()
        try:
            return self._factories[key]()
        except KeyError as error:
            raise ResearchConfigurationError(
                f"unknown research search provider: {name}"
            ) from error

    def names(self) -> list[str]:
        return sorted(self._factories)


def default_provider_registry() -> ResearchProviderRegistry:
    registry = ResearchProviderRegistry()
    registry.register("zhipu", ZhipuWebSearchProvider)
    registry.register("zhipu-web-search", ZhipuWebSearchProvider)
    registry.register("brave-web-search", BraveWebSearchProvider)
    registry.register("brave-image-search", BraveImageSearchProvider)
    registry.register("lane-routed", default_lane_routed_provider)
    return registry
