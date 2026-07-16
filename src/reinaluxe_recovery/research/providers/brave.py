"""Brave Search provider contracts with secret-safe bounded requests."""

from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import httpx

from reinaluxe_recovery.community.normalization import stable_id
from reinaluxe_recovery.research.contracts import ResearchQuery
from reinaluxe_recovery.research.errors import ResearchConfigurationError, ResearchError
from reinaluxe_recovery.research.providers.base import ResearchSearchProvider

DEFAULT_WEB_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
DEFAULT_IMAGE_ENDPOINT = "https://api.search.brave.com/res/v1/images/search"


class BraveWebSearchProvider(ResearchSearchProvider):
    """Brave Web Search adapter; it never crawls returned result pages."""

    provider_name = "brave-web-search"

    def __init__(
        self,
        *,
        environ: Mapping[str, str] | None = None,
        client: httpx.Client | None = None,
        endpoint: str = DEFAULT_WEB_ENDPOINT,
        timeout_seconds: float = 30.0,
        result_count: int = 10,
    ) -> None:
        if not 1 <= result_count <= 10:
            raise ValueError("Brave result_count must be between 1 and 10")
        values = os.environ if environ is None else environ
        self._api_key = values.get("BRAVE_SEARCH_API_KEY", "").strip()
        self._client = client
        self._endpoint = endpoint
        self._timeout_seconds = timeout_seconds
        self._requested_result_count = result_count
        self._query_calls = 0
        self._result_count = 0

    def __repr__(self) -> str:
        return (
            "BraveWebSearchProvider("
            f"configured={bool(self._api_key)}, endpoint={self._endpoint!r})"
        )

    def validate_configuration(self) -> None:
        if not self._api_key:
            raise ResearchConfigurationError(
                "Brave configuration is incomplete; missing BRAVE_SEARCH_API_KEY"
            )

    def capabilities(self) -> Mapping[str, Any]:
        return {
            "provider": self.provider_name,
            "web_search": True,
            "image_search": False,
            "result_page_crawling": False,
            "requested_result_count": self._requested_result_count,
        }

    def execute_query(self, query: ResearchQuery) -> Any:
        self.validate_configuration()
        count = min(self._requested_result_count, query.maximum_results, 10)
        client = self._client or httpx.Client(timeout=self._timeout_seconds)
        owns_client = self._client is None
        try:
            response = client.get(
                self._endpoint,
                headers={
                    "Accept": "application/json",
                    "X-Subscription-Token": self._api_key,
                },
                params={
                    "q": query.exact_search_query,
                    "count": count,
                    "safesearch": "moderate",
                    "search_lang": query.language,
                    "text_decorations": "false",
                },
            )
            response.raise_for_status()
            value = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise ResearchError(
                f"Brave web search failed for query {query.query_id}; "
                "credentials were redacted"
            ) from error
        finally:
            if owns_client:
                client.close()
        self._query_calls += 1
        return value

    def normalize_results(
        self, query: ResearchQuery, response: Any
    ) -> list[dict[str, Any]]:
        items: Any = []
        if isinstance(response, dict):
            web = response.get("web", {})
            if isinstance(web, dict):
                items = web.get("results", [])
        if not isinstance(items, list):
            raise ResearchError(
                f"Brave returned an unsupported response for query {query.query_id}"
            )
        output: list[dict[str, Any]] = []
        for rank, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            url = item.get("url")
            if not isinstance(url, str) or not url.strip():
                continue
            profile = item.get("profile")
            provider_result_id = item.get("id") or stable_id(
                "brave_result",
                {"query_id": query.query_id, "rank": rank, "url": url},
            )
            output.append(
                {
                    "url": url,
                    "provider_result_id": str(provider_result_id),
                    "provider_result_identifier_origin": (
                        "provider" if item.get("id") else "derived"
                    ),
                    "title": item.get("title"),
                    "snippet": item.get("description"),
                    "published_at": item.get("page_age") or item.get("age"),
                    "language": item.get("language"),
                    "images": [],
                    "rank": rank,
                    "retrieved_at": datetime.now(UTC).isoformat(),
                    "provider_access_classification": "provider_returned_snippet",
                    "provider_metadata": {
                        "profile": profile if isinstance(profile, dict) else {},
                        "provider_result_identifier_origin": (
                            "provider" if item.get("id") else "derived"
                        ),
                    },
                }
            )
        self._result_count += len(output)
        return output

    def report_usage(self) -> Mapping[str, Any]:
        return {
            "provider": self.provider_name,
            "query_calls": self._query_calls,
            "normalized_results": self._result_count,
            "requested_result_count": self._requested_result_count,
            "credentials_serialized": False,
            "result_page_requests": 0,
            "retry_count": 0,
        }


class BraveImageSearchProvider(ResearchSearchProvider):
    """Brave image-search contract with live execution disabled for this stage."""

    provider_name = "brave-image-search"

    def __init__(
        self,
        *,
        environ: Mapping[str, str] | None = None,
        endpoint: str = DEFAULT_IMAGE_ENDPOINT,
        result_count: int = 10,
    ) -> None:
        if not 1 <= result_count <= 10:
            raise ValueError("Brave image result_count must be between 1 and 10")
        values = os.environ if environ is None else environ
        self._api_key = values.get("BRAVE_SEARCH_API_KEY", "").strip()
        self._endpoint = endpoint
        self._requested_result_count = result_count
        self._normalize_calls = 0

    def __repr__(self) -> str:
        return (
            "BraveImageSearchProvider("
            f"configured={bool(self._api_key)}, live_execution=False)"
        )

    def validate_configuration(self) -> None:
        if not self._api_key:
            raise ResearchConfigurationError(
                "Brave configuration is incomplete; missing BRAVE_SEARCH_API_KEY"
            )

    def capabilities(self) -> Mapping[str, Any]:
        return {
            "provider": self.provider_name,
            "web_search": False,
            "image_search": True,
            "live_execution": False,
            "image_downloads": False,
            "requested_result_count": self._requested_result_count,
        }

    def execute_query(self, query: ResearchQuery) -> Any:
        del query
        raise ResearchError(
            "live Brave image search is disabled for Stage 009C-Core-1C"
        )

    def normalize_results(
        self, query: ResearchQuery, response: Any
    ) -> list[dict[str, Any]]:
        items = response.get("results", []) if isinstance(response, dict) else []
        if not isinstance(items, list):
            raise ResearchError(
                f"Brave image search returned an unsupported response for {query.query_id}"
            )
        output: list[dict[str, Any]] = []
        for rank, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            page_url = item.get("url") or item.get("source")
            image_url = (
                item.get("properties", {}).get("url")
                if isinstance(item.get("properties"), dict)
                else None
            )
            if not isinstance(page_url, str) or not page_url.strip():
                continue
            output.append(
                {
                    "url": page_url,
                    "provider_result_id": str(
                        item.get("id")
                        or stable_id(
                            "brave_image_result",
                            {"query_id": query.query_id, "rank": rank, "url": page_url},
                        )
                    ),
                    "title": item.get("title"),
                    "snippet": item.get("description"),
                    "images": [image_url] if isinstance(image_url, str) else [],
                    "rank": rank,
                    "provider_access_classification": "metadata_only",
                    "provider_metadata": {"live_execution": False},
                }
            )
        self._normalize_calls += 1
        return output

    def report_usage(self) -> Mapping[str, Any]:
        return {
            "provider": self.provider_name,
            "query_calls": 0,
            "normalize_calls": self._normalize_calls,
            "requested_result_count": self._requested_result_count,
            "credentials_serialized": False,
            "images_downloaded": 0,
            "live_execution": False,
        }
