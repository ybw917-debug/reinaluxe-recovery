"""Research provider interfaces and implementations."""

from reinaluxe_recovery.research.providers.base import (
    ResearchSearchProvider,
    VisualAnalysisProvider,
)
from reinaluxe_recovery.research.providers.brave import (
    BraveImageSearchProvider,
    BraveWebSearchProvider,
)
from reinaluxe_recovery.research.providers.registry import (
    ResearchProviderRegistry,
    default_provider_registry,
)
from reinaluxe_recovery.research.providers.routing import (
    LaneRoutedSearchProvider,
    RoutedProviderResponse,
    default_lane_routed_provider,
)
from reinaluxe_recovery.research.providers.zhipu import ZhipuWebSearchProvider
from reinaluxe_recovery.research.providers.zhipu_analysis import ZhipuGLMSourceAnalyzer

__all__ = [
    "BraveImageSearchProvider",
    "BraveWebSearchProvider",
    "LaneRoutedSearchProvider",
    "ResearchProviderRegistry",
    "ResearchSearchProvider",
    "RoutedProviderResponse",
    "VisualAnalysisProvider",
    "ZhipuWebSearchProvider",
    "ZhipuGLMSourceAnalyzer",
    "default_lane_routed_provider",
    "default_provider_registry",
]
