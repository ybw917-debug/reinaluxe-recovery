"""Zhipu web-search provider with secret-safe configuration and reporting."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

import httpx

from reinaluxe_recovery.research.contracts import ResearchQuery
from reinaluxe_recovery.research.errors import ResearchConfigurationError, ResearchError
from reinaluxe_recovery.research.providers.base import ResearchSearchProvider

DEFAULT_SEARCH_ENDPOINT = "https://open.bigmodel.cn/api/paas/v4/web_search"


class ZhipuWebSearchProvider(ResearchSearchProvider):
    """First provider implementation; credentials never enter artifacts or reprs."""

    provider_name = "zhipu"

    def __init__(
        self,
        *,
        environ: Mapping[str, str] | None = None,
        client: httpx.Client | None = None,
        endpoint: str = DEFAULT_SEARCH_ENDPOINT,
        timeout_seconds: float = 30.0,
    ) -> None:
        values = os.environ if environ is None else environ
        self._api_key = values.get("ZHIPU_API_KEY", "").strip()
        self._search_engine = values.get("ZHIPU_SEARCH_ENGINE", "").strip()
        self._summarizer_model = values.get("ZHIPU_SUMMARIZER_MODEL", "").strip()
        self._client = client
        self._endpoint = endpoint
        self._timeout_seconds = timeout_seconds
        self._query_calls = 0
        self._result_count = 0

    def __repr__(self) -> str:
        return (
            "ZhipuWebSearchProvider("
            f"configured={bool(self._api_key and self._search_engine and self._summarizer_model)}, "
            f"endpoint={self._endpoint!r})"
        )

    def validate_configuration(self) -> None:
        missing = [
            name
            for name, value in (
                ("ZHIPU_API_KEY", self._api_key),
                ("ZHIPU_SEARCH_ENGINE", self._search_engine),
                ("ZHIPU_SUMMARIZER_MODEL", self._summarizer_model),
            )
            if not value
        ]
        if missing:
            raise ResearchConfigurationError(
                "Zhipu configuration is incomplete; missing " + ", ".join(missing)
            )

    def capabilities(self) -> Mapping[str, Any]:
        return {
            "provider": self.provider_name,
            "web_search": True,
            "image_metadata": True,
            "alternate_languages": True,
            "summarizer_configured": bool(self._summarizer_model),
            "search_engine_configured": bool(self._search_engine),
        }

    def execute_query(self, query: ResearchQuery) -> Any:
        self.validate_configuration()
        payload: dict[str, Any] = {
            "search_query": query.search_text[:70],
            "search_engine": self._search_engine,
            "search_intent": False,
            "count": 10,
            "search_recency_filter": "noLimit",
            "content_size": "high",
        }
        client = self._client or httpx.Client(timeout=self._timeout_seconds)
        owns_client = self._client is None
        try:
            response = client.post(
                self._endpoint,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=payload,
            )
            response.raise_for_status()
            value = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise ResearchError(
                f"Zhipu search failed for query {query.query_id}; credentials were redacted"
            ) from error
        finally:
            if owns_client:
                client.close()
        self._query_calls += 1
        return value

    def normalize_results(
        self, query: ResearchQuery, response: Any
    ) -> list[dict[str, Any]]:
        items: Any
        if isinstance(response, dict):
            items = response.get("search_result", response.get("results", []))
            if isinstance(items, dict):
                items = items.get("items", [])
        else:
            items = response
        if not isinstance(items, list):
            raise ResearchError(
                f"Zhipu returned an unsupported response for query {query.query_id}"
            )
        output: list[dict[str, Any]] = []
        for rank, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            url = item.get("link") or item.get("url")
            if not isinstance(url, str) or not url.strip():
                continue
            image_values = item.get("images") or item.get("image_urls") or []
            if isinstance(image_values, str):
                image_values = [image_values]
            images: list[dict[str, Any] | str] = (
                list(image_values) if isinstance(image_values, list) else []
            )
            output.append(
                {
                    "url": url,
                    "title": item.get("title"),
                    "snippet": item.get("content") or item.get("snippet"),
                    "published_at": item.get("publish_date")
                    or item.get("published_at"),
                    "language": item.get("language"),
                    "images": images,
                    "rank": rank,
                    "provider_metadata": {
                        "media": item.get("media"),
                        "refer": item.get("refer"),
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
            "credentials_serialized": False,
            "search_engine": self._search_engine,
            "summarizer_model": self._summarizer_model,
        }
