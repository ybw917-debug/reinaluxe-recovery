"""Optional GLM-assisted analysis of already-screened Zhipu results."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from typing import Any

import httpx

from reinaluxe_recovery.research.analysis import (
    SourceAnalysisProvider,
    SourceAnalysisResult,
)
from reinaluxe_recovery.research.contracts import ResearchPlan, SourceCandidate
from reinaluxe_recovery.research.errors import ResearchConfigurationError, ResearchError

DEFAULT_CHAT_ENDPOINT = "https://open.bigmodel.cn/api/paas/v4/chat/completions"


class ZhipuGLMSourceAnalyzer(SourceAnalysisProvider):
    """Analyze provider-returned metadata without inventing or accepting new URLs."""

    def __init__(
        self,
        *,
        environ: Mapping[str, str] | None = None,
        client: httpx.Client | None = None,
        endpoint: str = DEFAULT_CHAT_ENDPOINT,
    ) -> None:
        values = os.environ if environ is None else environ
        self._api_key = values.get("ZHIPU_API_KEY", "").strip()
        self._model = values.get("ZHIPU_SUMMARIZER_MODEL", "").strip()
        self._client = client
        self._endpoint = endpoint

    def analyze(
        self, source: SourceCandidate, plan: ResearchPlan
    ) -> SourceAnalysisResult:
        if not self._api_key or not self._model:
            raise ResearchConfigurationError(
                "GLM analysis requires ZHIPU_API_KEY and ZHIPU_SUMMARIZER_MODEL"
            )
        prompt = {
            "instruction": (
                "Analyze only this screened public-source record. Return JSON with relevance, "
                "first_hand_status, specificity, commercial_promotion_risk, source_access_quality, "
                "evidence_summary, claims, limitations, proposed_topic_ids, and "
                "proposed_article_sections. Split claims atomically. Do not add URLs, infer image "
                "authenticity/provenance, or expose private identities."
            ),
            "research_id": plan.research_id,
            "source": source.model_dump(mode="json"),
        }
        client = self._client or httpx.Client(timeout=45.0)
        owns_client = self._client is None
        try:
            response = client.post(
                self._endpoint,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": "Return one strict JSON object."},
                        {
                            "role": "user",
                            "content": json.dumps(prompt, ensure_ascii=False),
                        },
                    ],
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                },
            )
            response.raise_for_status()
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
            value: Any = json.loads(content)
            if not isinstance(value, dict):
                raise ValueError("analysis response is not an object")
            # The analyzer cannot add a SourceCandidate; source identity remains immutable.
            return SourceAnalysisResult.model_validate(value)
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as error:
            raise ResearchError(
                f"GLM analysis failed for source {source.source_id}; credentials were redacted"
            ) from error
        finally:
            if owns_client:
                client.close()
