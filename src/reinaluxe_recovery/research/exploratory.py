"""Bounded exploratory editorial research and generative enrichment workflow."""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from collections import Counter, defaultdict
from collections.abc import Mapping
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal, cast
from urllib.parse import urlsplit

import httpx
from pydantic import Field

from reinaluxe_recovery.community.io import (
    prepare_output,
    write_csv,
    write_json,
    write_text,
)
from reinaluxe_recovery.community.normalization import normalize_text, stable_id
from reinaluxe_recovery.domain.base import DomainModel, NonEmptyText
from reinaluxe_recovery.research.artifacts import load_research_request
from reinaluxe_recovery.research.contracts import (
    ArticleResearchRequest,
    ResearchPlan,
    ResearchQuery,
    SourceLane,
)
from reinaluxe_recovery.research.errors import ResearchConfigurationError, ResearchError
from reinaluxe_recovery.research.planning import build_research_plan
from reinaluxe_recovery.research.providers import (
    BraveWebSearchProvider,
    ResearchSearchProvider,
    ZhipuWebSearchProvider,
)
from reinaluxe_recovery.research.screening import (
    classify_source_lane_details,
    is_corrupted_content,
    normalize_source_url,
)

DEFAULT_CHAT_ENDPOINT = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
_URL = re.compile(r"https?://|www\.", re.IGNORECASE)
_OWNER_FABRICATION = re.compile(
    r"\b(?:i|we|our team|reinaluxe)\s+(?:handled|received|photographed|measured|tested|visited|inspected)\b",
    re.IGNORECASE,
)
_PURCHASE_ASSISTANCE = re.compile(
    r"\b(?:where to buy|buy from|contact (?:the )?seller|order from|seller contact|purchase link)\b",
    re.IGNORECASE,
)
_PRECISE_MEASUREMENT = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:g|kg|mm|cm|inches?|grams?)\b", re.IGNORECASE
)
_MALWARE = ("malware", "phishing", "download crack", "virus detected")
_PSP_GAMING = ("playstation portable", "sony psp", "psp game", "handheld console")
_SPAM = (
    "keyword keyword keyword",
    "click here click here",
    "best cheap replica wholesale",
)


class InformationClass(StrEnum):
    DIRECTLY_SUPPORTED_FACT = "directly_supported_fact"
    ATTRIBUTED_COMMUNITY_REPORT = "attributed_community_report"
    ATTRIBUTED_COMMERCIAL_CLAIM = "attributed_commercial_claim"
    MARKET_OBSERVATION = "market_observation"
    MARKET_PATTERN = "market_pattern"
    EDITORIAL_INFERENCE = "editorial_inference"
    BUYER_GUIDANCE = "buyer_guidance"
    VISUAL_INTERPRETATION = "visual_interpretation"
    RESEARCH_HYPOTHESIS = "research_hypothesis"
    FOLLOW_UP_QUERY = "follow_up_query"


class ExploratoryQuery(DomainModel):
    query_id: str
    round: Literal[1, 2]
    query_family: NonEmptyText
    exact_search_query: NonEmptyText
    language: NonEmptyText = "en"
    target_provider: Literal["brave-web-search", "zhipu-web-search"]
    target_lane: SourceLane
    originating_source_ids: list[str] = Field(default_factory=list)
    originating_theme: str = "initial article scope"
    expansion_rationale: NonEmptyText
    expected_information_gain: NonEmptyText
    query_style: NonEmptyText
    maximum_results: int = Field(default=10, ge=1, le=10)

    def as_research_query(self) -> ResearchQuery:
        return ResearchQuery.model_validate(
            {
                "query_id": self.query_id,
                "research_question_id": stable_id(
                    "exploratory_question", self.query_family
                ),
                "query_family": self.query_family,
                "source_lane": self.target_lane,
                "requested_source_lane": self.target_lane,
                "search_text": self.exact_search_query,
                "exact_search_query": self.exact_search_query,
                "maximum_results": self.maximum_results,
                "expected_evidence_type": "exploratory market information",
                "stopping_criteria": "bounded by the configured exploratory call budget",
                "language": self.language,
                "clear_research_question": self.expected_information_gain,
                "query_generation_inputs": {
                    "round": self.round,
                    "target_provider": self.target_provider,
                    "originating_theme": self.originating_theme,
                    "query_style": self.query_style,
                },
            }
        )


class SourceUtilityScore(DomainModel):
    topic_relevance: float = Field(ge=0, le=1)
    novelty: float = Field(ge=0, le=1)
    buyer_language_value: float = Field(ge=0, le=1)
    terminology_value: float = Field(ge=0, le=1)
    visual_value: float = Field(ge=0, le=1)
    pattern_value: float = Field(ge=0, le=1)
    contradiction_value: float = Field(ge=0, le=1)
    query_expansion_value: float = Field(ge=0, le=1)
    publication_value: float = Field(ge=0, le=1)
    factual_reliability: float = Field(ge=0, le=1)


class ExploratorySource(DomainModel):
    source_id: str
    query_id: str
    query_family: str
    round: Literal[1, 2]
    provider: NonEmptyText
    provider_result_id: str | None = None
    source_url: str
    normalized_url: str
    title: str = ""
    snippet: str = ""
    target_lane: SourceLane
    classified_lane: SourceLane
    classification_rule: str
    source_purpose: str
    commercial_risk: Literal["low", "medium", "high"]
    independence_risk: Literal["low", "medium", "high"]
    likely_usefulness: list[str]
    allowed_editorial_uses: list[str]
    prohibited_factual_uses: list[str]
    utility: SourceUtilityScore
    has_visual_metadata: bool = False
    retrieved_at: str


class ExploratoryAnalysisProvider(ABC):
    @abstractmethod
    def expand_queries(
        self,
        sources: list[ExploratorySource],
        *,
        maximum_queries: int,
    ) -> list[dict[str, Any]]:
        """Propose one bounded second-round plan from retained sources."""

    @abstractmethod
    def run_stage(self, stage: str, context: Mapping[str, Any]) -> list[dict[str, Any]]:
        """Return structured records for one named synthesis stage."""


class GLMExploratoryAnalysisProvider(ExploratoryAnalysisProvider):
    """GLM analysis, expansion, and synthesis over provider-returned records only."""

    def __init__(
        self,
        *,
        environ: Mapping[str, str] | None = None,
        client: httpx.Client | None = None,
        endpoint: str = DEFAULT_CHAT_ENDPOINT,
    ) -> None:
        import os

        values = os.environ if environ is None else environ
        self._api_key = values.get("ZHIPU_API_KEY", "").strip()
        self._model = values.get("ZHIPU_SUMMARIZER_MODEL", "").strip()
        self._client = client
        self._endpoint = endpoint
        self._calls: Counter[str] = Counter()

    def expand_queries(
        self,
        sources: list[ExploratorySource],
        *,
        maximum_queries: int,
    ) -> list[dict[str, Any]]:
        payload = {
            "task": "bounded iterative query expansion",
            "maximum_queries": maximum_queries,
            "allowed_providers": ["brave-web-search", "zhipu-web-search"],
            "allowed_lanes": [
                item.value for item in SourceLane if item is not SourceLane.VISUAL_IMAGE
            ],
            "requirements": [
                "identify emerging terms, recurring problems, disagreements, adjacent domains, missing buyer questions, model references, and image opportunities",
                "each query must cite originating source IDs and remain analytical rather than offer purchasing assistance",
                "use Chinese with zhipu-web-search when useful",
                "return JSON object with records array only",
            ],
            "sources": [_source_prompt(item) for item in sources[:60]],
        }
        return self._request("query_expansion", payload)[:maximum_queries]

    def run_stage(self, stage: str, context: Mapping[str, Any]) -> list[dict[str, Any]]:
        payload = {
            "task": stage,
            "information_classes": [item.value for item in InformationClass],
            "rules": [
                "link every observation, pattern, inference, guidance item, and module to supplied source IDs",
                "market patterns and editorial inferences may synthesize incomplete linked observations",
                "summarize reasoning but do not provide hidden chain of thought",
                "never invent owner experience, customer cases, measurements, URLs, tests, factory visits, supplier documents, or tannery confirmation",
                "do not provide counterfeit sourcing or purchasing assistance",
                "return JSON object with records array only",
            ],
            "context": context,
        }
        return self._request(stage, payload)

    def report_usage(self) -> dict[str, Any]:
        return {
            "model": self._model,
            "stage_calls": dict(sorted(self._calls.items())),
            "credentials_serialized": False,
            "retry_count": 0,
        }

    def _request(self, stage: str, payload: Mapping[str, Any]) -> list[dict[str, Any]]:
        if not self._api_key or not self._model:
            raise ResearchConfigurationError(
                "exploratory GLM analysis requires ZHIPU_API_KEY and ZHIPU_SUMMARIZER_MODEL"
            )
        client = self._client or httpx.Client(timeout=90.0)
        owns_client = self._client is None
        try:
            response = client.post(
                self._endpoint,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "model": self._model,
                    "messages": [
                        {
                            "role": "system",
                            "content": "Return strict JSON. Be concise, source-linked, useful, and non-fabricated.",
                        },
                        {
                            "role": "user",
                            "content": json.dumps(payload, ensure_ascii=False),
                        },
                    ],
                    "temperature": 0.2,
                    "response_format": {"type": "json_object"},
                },
            )
            response.raise_for_status()
            value = json.loads(response.json()["choices"][0]["message"]["content"])
            records = value.get("records", []) if isinstance(value, dict) else []
            if not isinstance(records, list) or not all(
                isinstance(item, dict) for item in records
            ):
                raise ValueError("records must be an object array")
        except (
            httpx.HTTPError,
            KeyError,
            IndexError,
            ValueError,
            json.JSONDecodeError,
        ) as error:
            raise ResearchError(
                f"GLM exploratory stage {stage} failed; credentials were redacted"
            ) from error
        finally:
            if owns_client:
                client.close()
        self._calls[stage] += 1
        return [dict(item) for item in records]


_FAMILY_SPECS: tuple[tuple[str, SourceLane, tuple[tuple[str, str, str], ...]], ...] = (
    (
        "terminology_and_tiers",
        SourceLane.COMMUNITY_REDDIT,
        (
            (
                "replica bag quality tiers AAA mirror quality high tier meaning",
                "en",
                "direct",
            ),
            (
                "site:reddit.com/r/ replica bags tier labels seller terminology",
                "en",
                "colloquial",
            ),
            ("复刻包 等级 原版皮 顶级 术语 区别", "zh-CN", "synonym"),
        ),
    ),
    (
        "buyer_experiences",
        SourceLane.COMMUNITY_REDDIT,
        (
            (
                "replica handbag buyer experience expectations versus received quality",
                "en",
                "buyer-experience",
            ),
            (
                "site:reddit.com/r/ replica bag what surprised buyers quality",
                "en",
                "problem-oriented",
            ),
            ("复刻包 买家 收到 实物 质量 体验 差异", "zh-CN", "buyer-experience"),
        ),
    ),
    (
        "psp_and_qc",
        SourceLane.COMMUNITY_FORUMS,
        (
            (
                "replica handbag pre shipment photos QC lighting received item comparison",
                "en",
                "comparison",
            ),
            (
                "bag QC photos color lighting white balance visible defects",
                "en",
                "adjacent-domain",
            ),
            ("包包 出货照 QC 图片 灯光 色差 实物", "zh-CN", "problem-oriented"),
        ),
    ),
    (
        "seller_consistency",
        SourceLane.COMMUNITY_REDDIT,
        (
            (
                "replica bag seller descriptions batch consistency buyer reports",
                "en",
                "buyer-experience",
            ),
            (
                "replica handbags same seller quality variation discussion",
                "en",
                "problem-oriented",
            ),
            ("复刻包 卖家 描述 批次 质量 稳定性", "zh-CN", "commercial-language"),
        ),
    ),
    (
        "materials_and_leather_claims",
        SourceLane.EXPERT_EDITORIAL,
        (
            (
                "replica handbag original leather imported leather material claims",
                "en",
                "commercial-language",
            ),
            (
                "luxury leather grain temper finish observable quality guide",
                "en",
                "adjacent-domain",
            ),
            ("复刻包 原版皮 进口皮 皮料 来源 宣传", "zh-CN", "synonym"),
        ),
    ),
    (
        "handmade_and_craftsmanship",
        SourceLane.EXPERT_EDITORIAL,
        (
            (
                "replica handbag handmade craftsmanship claims stitching edge paint",
                "en",
                "direct",
            ),
            (
                "handbag stitching edge paint construction quality inspection",
                "en",
                "adjacent-domain",
            ),
            ("复刻包 手工 缝线 油边 工艺 宣传", "zh-CN", "commercial-language"),
        ),
    ),
    (
        "price_and_markup",
        SourceLane.COMMERCIAL_OBSERVATION,
        (
            (
                "replica bag tier price markup quality label market language",
                "en",
                "commercial-language",
            ),
            (
                "replica handbag price differences quality expectations discussion",
                "en",
                "comparison",
            ),
            ("复刻包 价格 加价 等级 品质 宣传", "zh-CN", "commercial-language"),
        ),
    ),
    (
        "quality_evaluation_methods",
        SourceLane.EXPERT_EDITORIAL,
        (
            (
                "handbag quality evaluation leather stitching hardware inspection",
                "en",
                "direct",
            ),
            (
                "how to inspect bag construction edge paint seams hardware finish",
                "en",
                "problem-oriented",
            ),
            ("包包 品质 检查 皮料 五金 缝线 油边", "zh-CN", "direct"),
        ),
    ),
    (
        "visual_comparison",
        SourceLane.EXPERT_EDITORIAL,
        (
            (
                "handbag visual comparison photography color distortion lighting",
                "en",
                "adjacent-domain",
            ),
            (
                "product photography white balance leather color texture limitations",
                "en",
                "adjacent-domain",
            ),
            ("包包 对比 图片 白平衡 灯光 颜色 误差", "zh-CN", "adjacent-domain"),
        ),
    ),
    (
        "sourcing_relationships",
        SourceLane.COMMUNITY_FORUMS,
        (
            (
                "replica handbag seller factory batch relationship claims discussion",
                "en",
                "market-language",
            ),
            (
                "informal supply chain product sampling batch variability handbags",
                "en",
                "adjacent-domain",
            ),
            ("复刻包 工厂 卖家 批次 供应链 说法", "zh-CN", "market-language"),
        ),
    ),
    (
        "risk_and_expectation_management",
        SourceLane.COMMUNITY_REDDIT,
        (
            (
                "replica bag buyer expectations risk QC limitations batch variation",
                "en",
                "buyer-experience",
            ),
            (
                "site:reddit.com/r/ replica bags managing expectations quality callouts",
                "en",
                "colloquial",
            ),
            ("复刻包 买家 预期 风险 品控 批次 差异", "zh-CN", "problem-oriented"),
        ),
    ),
    (
        "adjacent_inspection_knowledge",
        SourceLane.EXPERT_EDITORIAL,
        (
            (
                "leather behavior photography plating stitching edge paint quality control",
                "en",
                "adjacent-domain",
            ),
            (
                "product sampling supply chain variability visual inspection limitations",
                "en",
                "adjacent-domain",
            ),
            ("皮革 五金 电镀 缝线 油边 品控 检验", "zh-CN", "adjacent-domain"),
        ),
    ),
)


def build_exploratory_query_universe(research_id: str) -> list[ExploratoryQuery]:
    """Build twelve families with three broad query styles per family."""
    output: list[ExploratoryQuery] = []
    for family, lane, variants in _FAMILY_SPECS:
        for exact_query, language, style in variants:
            target: Literal["brave-web-search", "zhipu-web-search"] = (
                "zhipu-web-search" if language.startswith("zh") else "brave-web-search"
            )
            output.append(
                ExploratoryQuery(
                    query_id=stable_id(
                        "exploratory_query",
                        {
                            "research_id": research_id,
                            "family": family,
                            "query": exact_query,
                        },
                    ),
                    round=1,
                    query_family=family,
                    exact_search_query=exact_query,
                    language=language,
                    target_provider=target,
                    target_lane=lane,
                    expansion_rationale="Initial broad query universe for legacy reconstruction.",
                    expected_information_gain=f"Discover useful {family.replace('_', ' ')} information.",
                    query_style=style,
                )
            )
    return output


def score_source_utility(
    query: ExploratoryQuery,
    *,
    title: str,
    snippet: str,
    classified_lane: SourceLane,
    seen_terms: set[str] | None = None,
    has_visual_metadata: bool = False,
) -> SourceUtilityScore:
    """Score independent editorial utilities without a single pass/fail collapse."""
    text = normalize_text(f"{title} {snippet}").casefold()
    tokens = set(re.findall(r"[\w:]+", text))
    query_tokens = set(re.findall(r"[\w:]+", query.exact_search_query.casefold()))
    overlap = len(tokens & query_tokens) / max(1, min(8, len(query_tokens)))
    new = tokens - (seen_terms or set())
    community = classified_lane in {
        SourceLane.COMMUNITY_REDDIT,
        SourceLane.COMMUNITY_FORUMS,
    }
    commercial = classified_lane is SourceLane.COMMERCIAL_OBSERVATION
    buyer = any(
        word in text
        for word in ("buyer", "received", "experience", "expect", "买家", "实物")
    )
    terminology = any(
        word in text
        for word in ("tier", "aaa", "1:1", "mirror", "grade", "等级", "顶级")
    )
    contradiction = any(
        word in text
        for word in (
            "but",
            "however",
            "inconsistent",
            "varies",
            "disagree",
            "差异",
            "不一致",
        )
    )
    factual = (
        0.7
        if classified_lane in {SourceLane.PRIMARY_OFFICIAL, SourceLane.EXPERT_EDITORIAL}
        else 0.4
    )
    if commercial:
        factual = 0.2
    return SourceUtilityScore(
        topic_relevance=min(1.0, 0.2 + overlap),
        novelty=min(1.0, len(new) / 18),
        buyer_language_value=0.9 if buyer and community else 0.55 if buyer else 0.2,
        terminology_value=0.9 if terminology else 0.25,
        visual_value=0.9
        if has_visual_metadata
        else 0.5
        if "photo" in text or "image" in text or "图片" in text
        else 0.15,
        pattern_value=0.8
        if any(
            word in text
            for word in ("often", "common", "varies", "typically", "usually", "常见")
        )
        else 0.45,
        contradiction_value=0.85 if contradiction else 0.25,
        query_expansion_value=min(1.0, 0.35 + len(new) / 20),
        publication_value=min(
            1.0, 0.25 + overlap + (0.2 if buyer or terminology else 0)
        ),
        factual_reliability=factual,
    )


class DeterministicExploratoryAnalysisProvider(ExploratoryAnalysisProvider):
    """Offline fallback and synthetic-test analyzer grounded in retained records."""

    def expand_queries(
        self,
        sources: list[ExploratorySource],
        *,
        maximum_queries: int,
    ) -> list[dict[str, Any]]:
        ranked = sorted(
            sources,
            key=lambda item: (
                -item.utility.query_expansion_value,
                -item.utility.novelty,
                item.source_id,
            ),
        )
        templates = (
            (
                "lighting and white balance limitations for leather product photos",
                "photography limitations",
                SourceLane.EXPERT_EDITORIAL,
            ),
            (
                "handbag edge paint stitching inspection recurring defects",
                "construction inspection",
                SourceLane.EXPERT_EDITORIAL,
            ),
            (
                "replica bag batch variation buyer expectations discussion",
                "batch variability",
                SourceLane.COMMUNITY_REDDIT,
            ),
            (
                "leather temper grain finish observable quality differences",
                "leather behavior",
                SourceLane.EXPERT_EDITORIAL,
            ),
            (
                "handbag hardware plating finish visual inspection limits",
                "hardware finishing",
                SourceLane.EXPERT_EDITORIAL,
            ),
            (
                "informal supply chain product sampling consistency risk",
                "supply variability",
                SourceLane.EXPERT_EDITORIAL,
            ),
            (
                "replica handbag seller tier language disagreement",
                "unstable terminology",
                SourceLane.COMMUNITY_FORUMS,
            ),
            (
                "包包 QC 图片 灯光 白平衡 色差 局限",
                "Chinese visual terminology",
                SourceLane.EXPERT_EDITORIAL,
            ),
        )
        output: list[dict[str, Any]] = []
        for index, (query, theme, lane) in enumerate(templates[:maximum_queries]):
            source_ids = [item.source_id for item in ranked[index : index + 2]]
            output.append(
                {
                    "exact_search_query": query,
                    "language": "zh-CN"
                    if re.search(r"[\u4e00-\u9fff]", query)
                    else "en",
                    "target_provider": "zhipu-web-search"
                    if re.search(r"[\u4e00-\u9fff]", query)
                    else "brave-web-search",
                    "target_lane": lane.value,
                    "originating_source_ids": source_ids,
                    "originating_theme": theme,
                    "expansion_rationale": "Fill a recurring explanatory or buyer-question gap found in retained sources.",
                    "expected_information_gain": f"Clarify {theme} with additional context.",
                    "query_style": "adjacent-domain"
                    if "replica" not in query.casefold()
                    else "problem-oriented",
                }
            )
        return output

    def run_stage(self, stage: str, context: Mapping[str, Any]) -> list[dict[str, Any]]:
        sources = [
            dict(item) for item in context.get("sources", []) if isinstance(item, dict)
        ]
        source_ids = [
            str(item.get("source_id")) for item in sources if item.get("source_id")
        ]
        if stage == "source_understanding":
            records = []
            for item in sources[:20]:
                lane = str(item.get("classified_lane", ""))
                info = (
                    InformationClass.ATTRIBUTED_COMMERCIAL_CLAIM.value
                    if lane == SourceLane.COMMERCIAL_OBSERVATION.value
                    else InformationClass.ATTRIBUTED_COMMUNITY_REPORT.value
                    if lane
                    in {
                        SourceLane.COMMUNITY_REDDIT.value,
                        SourceLane.COMMUNITY_FORUMS.value,
                    }
                    else InformationClass.MARKET_OBSERVATION.value
                )
                records.append(
                    {
                        "observation_id": stable_id(
                            "observation", item.get("source_id")
                        ),
                        "information_class": info,
                        "summary": normalize_text(
                            str(
                                item.get("snippet")
                                or item.get("title")
                                or "Scoped market observation."
                            )
                        )[:300],
                        "source_ids": [item.get("source_id")],
                        "theme": str(item.get("query_family") or "market language"),
                        "confidence": 0.65,
                    }
                )
            return records
        if stage == "theme_extraction":
            families: dict[str, list[str]] = defaultdict(list)
            for item in sources:
                families[str(item.get("query_family") or "market_language")].append(
                    str(item.get("source_id"))
                )
            return [
                {
                    "theme_id": stable_id("theme", family),
                    "name": family.replace("_", " ").title(),
                    "summary": f"Sources surfaced recurring information about {family.replace('_', ' ')}.",
                    "source_ids": ids[:8],
                    "buyer_questions": [
                        f"How should readers interpret {family.replace('_', ' ')}?"
                    ],
                    "terminology": family.split("_"),
                }
                for family, ids in list(sorted(families.items()))[:12]
            ]
        if stage == "market_pattern_synthesis":
            themes = [
                dict(item)
                for item in context.get("themes", [])
                if isinstance(item, dict)
            ]
            return [
                {
                    "pattern_id": stable_id("pattern", item.get("theme_id")),
                    "information_class": InformationClass.MARKET_PATTERN.value,
                    "pattern": f"Descriptions of {str(item.get('name', 'market quality')).lower()} vary by source purpose and context rather than behaving like a universal standard.",
                    "source_ids": item.get("source_ids", []),
                    "reasoning_summary": "The linked records use overlapping language while emphasizing different observable signals and risks.",
                    "confidence": 0.7,
                    "limitation": "This is a scoped market synthesis, not verification of every seller or product.",
                }
                for item in themes[:10]
            ]
        if stage == "editorial_inference":
            patterns = [
                dict(item)
                for item in context.get("patterns", [])
                if isinstance(item, dict)
            ]
            return [
                {
                    "inference_id": stable_id("inference", item.get("pattern_id")),
                    "information_class": InformationClass.EDITORIAL_INFERENCE.value,
                    "inference": f"A practical reading of this pattern is to compare observable construction details and source consistency instead of relying on a label alone: {item.get('pattern', '')}",
                    "source_ids": item.get("source_ids", []),
                    "reasoning_summary": "The guidance follows from the linked pattern and its stated uncertainty.",
                    "confidence": 0.68,
                    "prohibited_extension": "Do not treat the inference as proof of origin, material composition, or universal performance.",
                }
                for item in patterns[:8]
            ]
        if stage == "contradiction_mapping":
            return (
                [
                    {
                        "contradiction_id": stable_id("contradiction", source_ids[:4]),
                        "topic": "Market labels versus observable quality",
                        "position_a": "Some descriptions present tier labels as stable quality categories.",
                        "position_b": "Community and editorial records describe quality and terminology as variable.",
                        "source_ids": source_ids[:6],
                        "editorial_treatment": "Present the disagreement as a reason to inspect evidence rather than repeat either position as universal fact.",
                    }
                ]
                if source_ids
                else []
            )
        if stage == "adjacent_domain_connection":
            return [
                {
                    "connection_id": stable_id("connection", name),
                    "source_domain": domain,
                    "target_domain": "replica handbag evaluation",
                    "connection_type": "explanatory analogy",
                    "connection_rationale": rationale,
                    "allowed_inference": allowed,
                    "prohibited_extension": "The adjacent source cannot verify a particular replica product or seller claim.",
                    "source_ids": source_ids[index : index + 3],
                }
                for index, (name, domain, rationale, allowed) in enumerate(
                    (
                        (
                            "white-balance",
                            "product photography",
                            "Lighting and white balance can shift recorded color.",
                            "Explain why PSP color differences require caution.",
                        ),
                        (
                            "leather-behavior",
                            "leather behavior",
                            "Grain, temper, and finish affect visible appearance.",
                            "Explain observable leather variation without asserting provenance.",
                        ),
                        (
                            "sampling",
                            "product sampling",
                            "Samples do not establish batch-wide consistency.",
                            "Explain why one photographed item cannot guarantee every item.",
                        ),
                    )
                )
                if source_ids[index : index + 3]
            ]
        if stage == "buyer_guidance_generation":
            patterns = [
                dict(item)
                for item in context.get("patterns", [])
                if isinstance(item, dict)
            ]
            return [
                {
                    "guidance_id": stable_id("guidance", item.get("pattern_id")),
                    "information_class": InformationClass.BUYER_GUIDANCE.value,
                    "guidance": "Treat market labels as a starting point and compare visible construction, disclosure consistency, and the limits of photographic evidence.",
                    "source_ids": item.get("source_ids", []),
                    "risk_addressed": "Overconfidence in informal tier or material-origin language.",
                    "confidence": 0.72,
                }
                for item in patterns[:6]
            ]
        if stage == "publication_module_generation":
            themes = [
                dict(item)
                for item in context.get("themes", [])
                if isinstance(item, dict)
            ]
            modules = []
            for index, item in enumerate(themes[:7]):
                name = str(item.get("name", "Market Quality"))
                ids = item.get("source_ids", [])
                modules.append(
                    {
                        "module_id": stable_id(
                            "publication_module", item.get("theme_id")
                        ),
                        "target_section": name,
                        "reader_question": f"What does {name.lower()} actually tell a reader?",
                        "proposed_heading": f"How to Read {name} Without Overinterpreting It",
                        "paragraphs": [
                            f"{name} is best understood as market language shaped by the source using it. Across the linked records, similar terms point to different combinations of visible finish, seller positioning, buyer expectations, and quality-control concerns. The useful conclusion is not that every label is meaningless, but that the label does not perform the work of inspection by itself.",
                            "A stronger evaluation starts with observable details and the conditions under which they were recorded. Photographs can reveal alignment, obvious surface defects, stitching rhythm, and some finishing differences, while lighting, compression, and angle can distort color and texture. Readers gain more from a consistent checklist than from treating one promotional phrase as a guarantee.",
                        ],
                        "supporting_source_ids": ids,
                        "synthesis_type": InformationClass.EDITORIAL_INFERENCE.value,
                        "confidence": 0.7,
                        "limitation": "The module summarizes linked market records and does not verify product origin.",
                        "internal_link_opportunity": "Link to a relevant quality-evaluation or materials guide.",
                        "image_opportunity": "Annotate an existing comparison image with visible-only inspection prompts.",
                        "expected_reader_value": "Helps readers translate unstable language into a practical evaluation method.",
                    }
                )
            return modules
        if stage == "overclaim_and_fabrication_review":
            modules = [
                dict(item)
                for item in context.get("modules", [])
                if isinstance(item, dict)
            ]
            return [
                {
                    "review_id": stable_id("overclaim_review", item.get("module_id")),
                    "module_id": item.get("module_id"),
                    "status": "accepted",
                    "reasons": [],
                    "revised_wording": "",
                }
                for item in modules
            ]
        return []


def run_exploratory_research(
    request_path: Path,
    output: Path,
    *,
    providers: Mapping[str, ResearchSearchProvider] | None = None,
    analyzer: ExploratoryAnalysisProvider | None = None,
    first_round_calls: int | None = None,
    second_round_calls: int | None = None,
) -> dict[str, Any]:
    """Run no more than two discovery rounds and export planning-only enrichment."""
    prepare_output(output)
    request = load_research_request(request_path)
    if not isinstance(request, ArticleResearchRequest):
        raise ResearchConfigurationError(
            "exploratory legacy research requires an article request"
        )
    plan = build_research_plan(request)
    first_budget = min(
        first_round_calls or request.first_round_call_budget, request.total_call_budget
    )
    second_budget = min(
        second_round_calls
        if second_round_calls is not None
        else request.second_round_call_budget,
        request.total_call_budget - first_budget,
    )
    if request.maximum_discovery_rounds < 2:
        second_budget = 0
    selected_providers = dict(
        providers
        or {
            "brave-web-search": BraveWebSearchProvider(result_count=10),
            "zhipu-web-search": ZhipuWebSearchProvider(result_count=10),
        }
    )
    selected_analyzer = analyzer or GLMExploratoryAnalysisProvider()
    universe = build_exploratory_query_universe(request.research_id)
    first_queries = _select_first_round(universe, first_budget)
    sources, calls, exclusions = _execute_round(
        first_queries, selected_providers, [], request.maximum_sources
    )
    expansion_error = ""
    try:
        proposed = selected_analyzer.expand_queries(
            sources, maximum_queries=second_budget
        )
    except ResearchError as error:
        expansion_error = str(error)
        proposed = DeterministicExploratoryAnalysisProvider().expand_queries(
            sources, maximum_queries=second_budget
        )
    second_queries = _normalize_expansion(
        request.research_id, proposed, sources, second_budget
    )
    if len(second_queries) < second_budget:
        fallback_proposed = DeterministicExploratoryAnalysisProvider().expand_queries(
            sources,
            maximum_queries=second_budget,
        )
        fallback_queries = _normalize_expansion(
            request.research_id,
            fallback_proposed,
            sources,
            second_budget,
        )
        existing_query_text = {
            item.exact_search_query.casefold() for item in second_queries
        }
        for fallback_query in fallback_queries:
            if fallback_query.exact_search_query.casefold() in existing_query_text:
                continue
            second_queries.append(fallback_query)
            existing_query_text.add(fallback_query.exact_search_query.casefold())
            if len(second_queries) >= second_budget:
                break
    second_sources: list[ExploratorySource] = []
    if second_queries:
        second_sources, second_calls, second_exclusions = _execute_round(
            second_queries,
            selected_providers,
            sources,
            request.maximum_sources - len(sources),
        )
        sources.extend(second_sources)
        calls.extend(second_calls)
        exclusions.extend(second_exclusions)
    stages, stage_errors = _run_synthesis_stages(selected_analyzer, sources, plan)
    validation = _export_exploratory(
        output,
        request,
        plan,
        universe,
        first_queries,
        second_queries,
        sources,
        calls,
        exclusions,
        stages,
        expansion_error,
        stage_errors,
        selected_analyzer,
    )
    return validation


def _select_first_round(
    universe: list[ExploratoryQuery], maximum_calls: int
) -> list[ExploratoryQuery]:
    by_family: dict[str, list[ExploratoryQuery]] = defaultdict(list)
    for query in universe:
        by_family[query.query_family].append(query)
    chinese_families = {
        "materials_and_leather_claims",
        "handmade_and_craftsmanship",
        "price_and_markup",
        "adjacent_inspection_knowledge",
    }
    selected = []
    for family, queries in by_family.items():
        preferred = next(
            (
                item
                for item in queries
                if family in chinese_families and item.language.startswith("zh")
            ),
            queries[0],
        )
        selected.append(preferred)
    if len(selected) < maximum_calls:
        selected_ids = {item.query_id for item in selected}
        selected.extend(item for item in universe if item.query_id not in selected_ids)
    return selected[:maximum_calls]


def _execute_round(
    queries: list[ExploratoryQuery],
    providers: Mapping[str, ResearchSearchProvider],
    existing_sources: list[ExploratorySource],
    maximum_new_sources: int,
) -> tuple[list[ExploratorySource], list[dict[str, Any]], list[dict[str, Any]]]:
    sources: list[ExploratorySource] = []
    calls: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    seen_urls = {item.normalized_url for item in existing_sources}
    seen_terms: set[str] = set()
    for item in existing_sources:
        seen_terms.update(
            re.findall(r"[\w:]+", f"{item.title} {item.snippet}".casefold())
        )
    for call_index, query in enumerate(queries, start=1):
        provider = providers.get(query.target_provider)
        if provider is None:
            raise ResearchConfigurationError(
                f"missing exploratory provider {query.target_provider}"
            )
        research_query = query.as_research_query()
        try:
            provider.validate_configuration()
            response = provider.execute_query(research_query)
            normalized = provider.normalize_results(research_query, response)[:10]
        except (ResearchError, ValueError) as error:
            calls.append(
                _call_row(call_index, query, 0, 0, "provider_failed", str(error))
            )
            continue
        calls.append(
            _call_row(
                call_index,
                query,
                _raw_count(response),
                len(normalized),
                "completed",
                "",
            )
        )
        for raw in normalized:
            source, reason = _retain_exploratory_source(
                query, provider.provider_name, raw, seen_terms
            )
            if source is None:
                exclusions.append(
                    {
                        "query_id": query.query_id,
                        "provider_result_id": raw.get("provider_result_id", ""),
                        "url": raw.get("url", ""),
                        "reason": reason or "unusable_result",
                    }
                )
                continue
            if source.normalized_url in seen_urls:
                exclusions.append(
                    {
                        "query_id": query.query_id,
                        "provider_result_id": source.provider_result_id or "",
                        "url": source.source_url,
                        "reason": "exact_duplicate_url",
                    }
                )
                continue
            if len(sources) >= maximum_new_sources:
                exclusions.append(
                    {
                        "query_id": query.query_id,
                        "provider_result_id": source.provider_result_id or "",
                        "url": source.source_url,
                        "reason": "maximum_sources_reached",
                    }
                )
                continue
            seen_urls.add(source.normalized_url)
            seen_terms.update(
                re.findall(r"[\w:]+", f"{source.title} {source.snippet}".casefold())
            )
            sources.append(source)
    return sources, calls, exclusions


def _retain_exploratory_source(
    query: ExploratoryQuery,
    provider_name: str,
    raw: Mapping[str, Any],
    seen_terms: set[str],
) -> tuple[ExploratorySource | None, str | None]:
    raw_url = raw.get("url")
    if not isinstance(raw_url, str) or not raw_url.strip():
        return None, "missing_url"
    try:
        normalized_url = normalize_source_url(raw_url)
    except (ValueError, UnicodeError):
        return None, "invalid_url"
    title = normalize_text(str(raw.get("title") or ""))
    snippet = normalize_text(str(raw.get("snippet") or ""))
    text = f"{title} {snippet}".casefold()
    host = (urlsplit(normalized_url).hostname or "").casefold()
    if any(marker in f"{host} {text}" for marker in _MALWARE):
        return None, "unsafe_page"
    if is_corrupted_content(f"{title} {snippet}"):
        return None, "irrecoverably_corrupted_text"
    if any(marker in text for marker in _SPAM):
        return None, "keyword_spam"
    if "psp" in query.query_family and any(marker in text for marker in _PSP_GAMING):
        return None, "wrong_semantic_meaning"
    classification = classify_source_lane_details(
        normalized_url, content=f"{title} {snippet}"
    )
    images = raw.get("images")
    has_visual = isinstance(images, list) and bool(images)
    utility = score_source_utility(
        query,
        title=title,
        snippet=snippet,
        classified_lane=classification.lane,
        seen_terms=seen_terms,
        has_visual_metadata=has_visual,
    )
    if utility.topic_relevance <= 0.2:
        return None, "clearly_unrelated"
    commercial = classification.lane is SourceLane.COMMERCIAL_OBSERVATION
    community = classification.lane in {
        SourceLane.COMMUNITY_REDDIT,
        SourceLane.COMMUNITY_FORUMS,
    }
    likely = [
        name
        for name, value in utility.model_dump().items()
        if name != "factual_reliability" and float(value) >= 0.6
    ]
    allowed = ["market_language", "query_expansion", "pattern_discovery"]
    if utility.publication_value >= 0.55:
        allowed.append("attributed_editorial_context")
    prohibited = ["verified_origin", "universal_quality_claim", "owner_experience"]
    if commercial:
        prohibited.extend(["verified_material_claim", "independent_confirmation"])
    return (
        ExploratorySource(
            source_id=stable_id("exploratory_source", normalized_url),
            query_id=query.query_id,
            query_family=query.query_family,
            round=query.round,
            provider=provider_name,
            provider_result_id=str(raw.get("provider_result_id") or "") or None,
            source_url=raw_url,
            normalized_url=normalized_url,
            title=title,
            snippet=snippet,
            target_lane=query.target_lane,
            classified_lane=classification.lane,
            classification_rule=classification.rule,
            source_purpose=(
                "commercial market language"
                if commercial
                else "buyer and community language"
                if community
                else "editorial or adjacent-domain context"
            ),
            commercial_risk="high" if commercial else "medium" if community else "low",
            independence_risk="high"
            if commercial
            else "medium"
            if community
            else "low",
            likely_usefulness=likely or ["query_expansion"],
            allowed_editorial_uses=allowed,
            prohibited_factual_uses=prohibited,
            utility=utility,
            has_visual_metadata=has_visual,
            retrieved_at=str(raw.get("retrieved_at") or datetime.now(UTC).isoformat()),
        ),
        None,
    )


def _normalize_expansion(
    research_id: str,
    proposed: list[dict[str, Any]],
    sources: list[ExploratorySource],
    maximum_queries: int,
) -> list[ExploratoryQuery]:
    valid_source_ids = {item.source_id for item in sources}
    output: list[ExploratoryQuery] = []
    seen: set[str] = set()
    for raw in proposed:
        exact = normalize_text(
            str(raw.get("exact_search_query") or raw.get("query") or "")
        )
        if not exact or _URL.search(exact) or exact.casefold() in seen:
            continue
        if _PURCHASE_ASSISTANCE.search(exact):
            continue
        target_provider_value = str(
            raw.get("target_provider") or "brave-web-search"
        ).casefold()
        if target_provider_value not in {"brave-web-search", "zhipu-web-search"}:
            continue
        target_provider = cast(
            Literal["brave-web-search", "zhipu-web-search"], target_provider_value
        )
        try:
            lane = SourceLane(
                str(raw.get("target_lane") or SourceLane.EXPERT_EDITORIAL.value)
            )
        except ValueError:
            continue
        if lane is SourceLane.VISUAL_IMAGE:
            lane = SourceLane.EXPERT_EDITORIAL
        origin_ids = sorted(
            {
                str(item)
                for item in raw.get("originating_source_ids", [])
                if str(item) in valid_source_ids
            }
        )
        if not origin_ids:
            continue
        language = str(raw.get("language") or "en")
        if language.startswith("zh"):
            target_provider = "zhipu-web-search"
        try:
            query = ExploratoryQuery(
                query_id=stable_id(
                    "exploratory_expansion_query",
                    {"research_id": research_id, "query": exact, "origin": origin_ids},
                ),
                round=2,
                query_family=str(raw.get("query_family") or "iterative_expansion"),
                exact_search_query=exact,
                language=language,
                target_provider=target_provider,
                target_lane=lane,
                originating_source_ids=origin_ids,
                originating_theme=str(
                    raw.get("originating_theme") or "emerging source theme"
                ),
                expansion_rationale=str(
                    raw.get("expansion_rationale")
                    or "Explore an information gap found in the first round."
                ),
                expected_information_gain=str(
                    raw.get("expected_information_gain")
                    or "Add useful context or resolve a disagreement."
                ),
                query_style=str(raw.get("query_style") or "problem-oriented"),
            )
        except ValueError:
            continue
        output.append(query)
        seen.add(exact.casefold())
        if len(output) >= maximum_queries:
            break
    return output


def _run_synthesis_stages(
    analyzer: ExploratoryAnalysisProvider,
    sources: list[ExploratorySource],
    plan: ResearchPlan,
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, str]]]:
    fallback = DeterministicExploratoryAnalysisProvider()
    source_payload = [item.model_dump(mode="json") for item in sources]
    sections = plan.article_analysis.headings if plan.article_analysis else []
    stages: dict[str, list[dict[str, Any]]] = {}
    errors: list[dict[str, str]] = []

    def run(
        stage: str,
        context: dict[str, Any],
        expected_fields: list[str],
        *,
        reject_urls: bool = True,
    ) -> list[dict[str, Any]]:
        payload = {**context, "expected_fields": expected_fields}
        try:
            records = analyzer.run_stage(stage, payload)
        except ResearchError as error:
            errors.append({"stage": stage, "error": str(error)})
            records = fallback.run_stage(stage, payload)
        if not records:
            errors.append({"stage": stage, "error": "empty structured stage output"})
            records = fallback.run_stage(stage, payload)
        return _sanitize_records(
            records,
            {item.source_id for item in sources},
            reject_urls=reject_urls,
        )

    stages["observations"] = run(
        "source_understanding",
        {"sources": source_payload},
        [
            "observation_id",
            "information_class",
            "summary",
            "source_ids",
            "theme",
            "confidence",
        ],
    )
    stages["themes"] = run(
        "theme_extraction",
        {"sources": source_payload, "observations": stages["observations"]},
        ["theme_id", "name", "summary", "source_ids", "buyer_questions", "terminology"],
    )
    stages["patterns"] = run(
        "market_pattern_synthesis",
        {
            "sources": source_payload,
            "themes": stages["themes"],
            "observations": stages["observations"],
        },
        [
            "pattern_id",
            "information_class",
            "pattern",
            "source_ids",
            "reasoning_summary",
            "confidence",
            "limitation",
        ],
    )
    stages["inferences"] = run(
        "editorial_inference",
        {"patterns": stages["patterns"], "observations": stages["observations"]},
        [
            "inference_id",
            "information_class",
            "inference",
            "source_ids",
            "reasoning_summary",
            "confidence",
            "prohibited_extension",
        ],
    )
    stages["contradictions"] = run(
        "contradiction_mapping",
        {"sources": source_payload, "patterns": stages["patterns"]},
        [
            "contradiction_id",
            "topic",
            "position_a",
            "position_b",
            "source_ids",
            "editorial_treatment",
        ],
    )
    stages["connections"] = run(
        "adjacent_domain_connection",
        {"sources": source_payload, "themes": stages["themes"]},
        [
            "connection_id",
            "source_domain",
            "target_domain",
            "connection_type",
            "connection_rationale",
            "allowed_inference",
            "prohibited_extension",
            "source_ids",
        ],
    )
    stages["guidance"] = run(
        "buyer_guidance_generation",
        {"patterns": stages["patterns"], "contradictions": stages["contradictions"]},
        [
            "guidance_id",
            "information_class",
            "guidance",
            "source_ids",
            "risk_addressed",
            "confidence",
        ],
    )
    stages["modules"] = run(
        "publication_module_generation",
        {
            "themes": stages["themes"],
            "patterns": stages["patterns"],
            "inferences": stages["inferences"],
            "guidance": stages["guidance"],
            "existing_sections": sections,
        },
        [
            "module_id",
            "target_section",
            "reader_question",
            "proposed_heading",
            "paragraphs",
            "supporting_source_ids",
            "synthesis_type",
            "confidence",
            "limitation",
            "internal_link_opportunity",
            "image_opportunity",
            "expected_reader_value",
        ],
        reject_urls=False,
    )
    model_reviews = run(
        "overclaim_and_fabrication_review",
        {"modules": stages["modules"]},
        ["review_id", "module_id", "status", "reasons", "revised_wording"],
    )
    stages["overclaims"], stages["modules"] = _final_overclaim_review(
        stages["modules"], model_reviews, {item.source_id for item in sources}
    )
    return stages, errors


def _sanitize_records(
    records: list[dict[str, Any]],
    valid_source_ids: set[str],
    *,
    reject_urls: bool = True,
) -> list[dict[str, Any]]:
    output = []
    for record in records:
        if reject_urls and _contains_url(record):
            continue
        cleaned = dict(record)
        for key in ("source_ids", "supporting_source_ids", "originating_source_ids"):
            if key in cleaned:
                value = cleaned[key] if isinstance(cleaned[key], list) else []
                cleaned[key] = sorted(
                    {str(item) for item in value if str(item) in valid_source_ids}
                )
        output.append(cleaned)
    return output


def _final_overclaim_review(
    modules: list[dict[str, Any]],
    model_reviews: list[dict[str, Any]],
    valid_source_ids: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    model_by_module = {str(item.get("module_id")): item for item in model_reviews}
    reviews: list[dict[str, Any]] = []
    accepted: list[dict[str, Any]] = []
    for module in modules:
        module_id = str(module.get("module_id") or stable_id("module", module))
        text = normalize_text(json.dumps(module, ensure_ascii=False))
        reasons = []
        if _URL.search(text):
            reasons.append("generated_source_url")
        if _OWNER_FABRICATION.search(text):
            reasons.append("fabricated_owner_experience")
        if _PURCHASE_ASSISTANCE.search(text):
            reasons.append("counterfeit_purchasing_assistance")
        if _PRECISE_MEASUREMENT.search(text):
            reasons.append("unsupported_precise_measurement")
        if (
            "tannery confirmed" in text.casefold()
            or "confirmed tannery" in text.casefold()
        ):
            reasons.append("unsupported_tannery_confirmation")
        supporting = module.get("supporting_source_ids", [])
        if (
            not isinstance(supporting, list)
            or not supporting
            or any(str(item) not in valid_source_ids for item in supporting)
        ):
            reasons.append("missing_or_invalid_source_links")
        model = model_by_module.get(module_id, {})
        if str(model.get("status", "accepted")).casefold() == "rejected":
            reasons.extend(str(item) for item in model.get("reasons", []) if str(item))
        status = "rejected" if reasons else "accepted"
        reviews.append(
            {
                "review_id": stable_id("overclaim_review", module_id),
                "module_id": module_id,
                "status": status,
                "reasons": sorted(set(reasons)),
                "revised_wording": model.get("revised_wording", ""),
            }
        )
        if status == "accepted":
            accepted.append({**module, "module_id": module_id})
    return reviews, accepted


def _export_exploratory(
    output: Path,
    request: ArticleResearchRequest,
    plan: ResearchPlan,
    universe: list[ExploratoryQuery],
    first_queries: list[ExploratoryQuery],
    second_queries: list[ExploratoryQuery],
    sources: list[ExploratorySource],
    calls: list[dict[str, Any]],
    exclusions: list[dict[str, Any]],
    stages: dict[str, list[dict[str, Any]]],
    expansion_error: str,
    stage_errors: list[dict[str, str]],
    analyzer: ExploratoryAnalysisProvider,
) -> dict[str, Any]:
    observations = stages["observations"]
    themes = stages["themes"]
    patterns = stages["patterns"]
    inferences = stages["inferences"]
    guidance = stages["guidance"]
    modules = stages["modules"]
    overclaims = stages["overclaims"]
    write_csv(
        output / "query-universe.csv",
        list(ExploratoryQuery.model_fields),
        [item.model_dump(mode="json") for item in universe],
    )
    write_csv(output / "provider-call-register.csv", _field_union(calls), calls)
    write_csv(
        output / "useful-source-candidates.csv",
        list(ExploratorySource.model_fields),
        [item.model_dump(mode="json") for item in sources],
    )
    write_csv(
        output / "source-exclusion-register.csv", _field_union(exclusions), exclusions
    )
    write_csv(
        output / "follow-up-query-plan.csv",
        list(ExploratoryQuery.model_fields),
        [item.model_dump(mode="json") for item in second_queries],
    )
    _write_records(output / "source-understanding-register.csv", observations)
    _write_records(output / "discovered-theme-register.csv", themes)
    _write_records(output / "market-pattern-register.csv", patterns)
    _write_records(output / "editorial-inference-register.csv", inferences)
    _write_records(output / "buyer-guidance-register.csv", guidance)
    _write_records(output / "contradiction-map.csv", stages["contradictions"])
    _write_records(output / "adjacent-domain-connections.csv", stages["connections"])
    _write_records(output / "overclaim-review.csv", overclaims)
    image_rows = _image_opportunities(sources, themes)
    _write_records(output / "image-analysis-opportunities.csv", image_rows)
    changes = _content_change_manifest(plan, modules)
    _write_records(output / "content-change-manifest.csv", changes)
    _write_publication_modules(output, modules)
    _write_section_copy(output, modules)
    provider_counts = Counter(item.provider for item in sources)
    lane_counts = Counter(item.classified_lane.value for item in sources)
    write_text(
        output / "research-landscape.md",
        (
            "# AAA exploratory research landscape\n\n"
            f"- Query families in universe: {len({item.query_family for item in universe})}\n"
            f"- Query variants in universe: {len(universe)}\n"
            f"- First-round calls: {len(first_queries)}\n"
            f"- Second-round calls: {len(second_queries)}\n"
            f"- Useful source candidates: {len(sources)}\n"
            f"- Themes: {len(themes)}\n"
            f"- Market observations: {len(observations)}\n"
            f"- Market patterns: {len(patterns)}\n"
            f"- Editorial inferences: {len(inferences)}\n"
            f"- Buyer guidance items: {len(guidance)}\n"
            f"- Adjacent-domain connections: {len(stages['connections'])}\n"
            f"- Publication modules accepted: {len(modules)}\n"
            f"- Overclaims rejected: {sum(item.get('status') == 'rejected' for item in overclaims)}\n\n"
            "## Provider coverage\n\n"
            + "\n".join(
                f"- {name}: {count} retained sources"
                for name, count in sorted(provider_counts.items())
            )
            + "\n\n## Classified lanes\n\n"
            + "\n".join(
                f"- {name}: {count}" for name, count in sorted(lane_counts.items())
            )
            + "\n\nCommercial, anecdotal, old, seller-authored, and lane-mismatched records were retained when they had editorial utility. Their allowed and prohibited uses remain explicit in the source register. No page was crawled and no image was downloaded.\n"
        ),
    )
    validation: dict[str, Any] = {
        "schema_version": "1.0",
        "research_id": request.research_id,
        "research_mode": request.mode.value,
        "discovery_rounds": 2 if second_queries else 1,
        "first_round_calls": len(first_queries),
        "second_round_calls": len(second_queries),
        "total_calls": len(calls),
        "retry_count": 0,
        "query_family_count": len({item.query_family for item in universe}),
        "query_universe_count": len(universe),
        "useful_source_candidates": len(sources),
        "themes": len(themes),
        "market_observations": len(observations),
        "market_patterns": len(patterns),
        "editorial_inferences": len(inferences),
        "buyer_guidance": len(guidance),
        "publication_modules": len(modules),
        "overclaims_rejected": sum(
            item.get("status") == "rejected" for item in overclaims
        ),
        "existing_sections_enriched": len(
            {item.get("target_section") for item in modules}
        ),
        "image_analysis_opportunities": len(image_rows),
        "expansion_error": expansion_error,
        "stage_errors": stage_errors,
        "safety": {
            "source_urls_generated": False,
            "result_pages_crawled": 0,
            "direct_reddit_requests": 0,
            "images_downloaded": 0,
            "wordpress_modified": False,
            "article_modified": False,
            "production_sqlite_modified": False,
            "automatic_third_round": False,
            "counterfeit_purchasing_assistance": False,
        },
        "analyzer_usage": analyzer.report_usage()
        if isinstance(analyzer, GLMExploratoryAnalysisProvider)
        else {"provider": "synthetic_or_deterministic"},
    }
    write_json(output / "exploratory-validation.json", validation)
    return validation


def _source_prompt(source: ExploratorySource) -> dict[str, Any]:
    return {
        "source_id": source.source_id,
        "query_family": source.query_family,
        "provider": source.provider,
        "classified_lane": source.classified_lane.value,
        "title": source.title[:240],
        "snippet": source.snippet[:600],
        "likely_usefulness": source.likely_usefulness,
        "factual_reliability": source.utility.factual_reliability,
        "query_expansion_value": source.utility.query_expansion_value,
    }


def _call_row(
    call_index: int,
    query: ExploratoryQuery,
    returned: int,
    processed: int,
    status: str,
    error: str,
) -> dict[str, Any]:
    return {
        "call_index_within_round": call_index,
        "round": query.round,
        "query_id": query.query_id,
        "query_family": query.query_family,
        "exact_search_query": query.exact_search_query,
        "language": query.language,
        "target_provider": query.target_provider,
        "target_lane": query.target_lane.value,
        "requested_result_limit": query.maximum_results,
        "returned_raw_results": returned,
        "processed_results": processed,
        "status": status,
        "error": normalize_text(error)[:300],
        "retry_count": 0,
    }


def _raw_count(response: Any) -> int:
    if not isinstance(response, dict):
        return len(response) if isinstance(response, list) else 0
    web = response.get("web")
    if isinstance(web, dict) and isinstance(web.get("results"), list):
        return len(web["results"])
    items = response.get("search_result", response.get("results", []))
    if isinstance(items, dict):
        items = items.get("items", [])
    return len(items) if isinstance(items, list) else 0


def _contains_url(value: object) -> bool:
    if isinstance(value, str):
        return bool(_URL.search(value))
    if isinstance(value, dict):
        return any(_contains_url(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_url(item) for item in value)
    return False


def _field_union(rows: list[dict[str, Any]]) -> list[str]:
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    return fields or ["schema_version"]


def _write_records(path: Path, rows: list[dict[str, Any]]) -> None:
    write_csv(path, _field_union(rows), rows)


def _image_opportunities(
    sources: list[ExploratorySource], themes: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    rows = []
    for source in sorted(
        sources,
        key=lambda item: (-item.utility.visual_value, item.source_id),
    )[:12]:
        if source.utility.visual_value < 0.45:
            continue
        rows.append(
            {
                "opportunity_id": stable_id("image_opportunity", source.source_id),
                "source_id": source.source_id,
                "theme": source.query_family.replace("_", " "),
                "opportunity": "Use an existing owner-approved image to explain visible-only inspection cues related to this source theme.",
                "analysis_prompt": "Compare alignment, stitching rhythm, edge finish, hardware finish, and lighting conditions without inferring provenance or tactile quality.",
                "prohibited_conclusion": "Do not infer authenticity, material origin, handling, weight, smell, or factory identity from appearance.",
                "image_download_required": False,
            }
        )
    if not rows and themes:
        rows.append(
            {
                "opportunity_id": stable_id(
                    "image_opportunity", themes[0].get("theme_id")
                ),
                "source_id": "",
                "theme": themes[0].get("name", "Visual evaluation"),
                "opportunity": "Apply a visible-only checklist to an existing approved comparison image.",
                "analysis_prompt": "Explain what the image can and cannot reveal under its lighting and angle.",
                "prohibited_conclusion": "Do not infer provenance or tactile qualities.",
                "image_download_required": False,
            }
        )
    return rows


def _content_change_manifest(
    plan: ResearchPlan, modules: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    headings = plan.article_analysis.headings if plan.article_analysis else []
    rows = []
    for index, module in enumerate(modules):
        proposed = str(module.get("target_section") or "")
        section = next(
            (
                heading
                for heading in headings
                if proposed.casefold() in heading.casefold()
                or heading.casefold() in proposed.casefold()
            ),
            headings[index % len(headings)]
            if headings
            else proposed or "Editorial enrichment",
        )
        rows.append(
            {
                "change_id": stable_id("exploratory_change", module.get("module_id")),
                "operation": "ENRICH" if section in headings else "ADD_AFTER",
                "target_section": section,
                "module_id": module.get("module_id"),
                "supporting_source_ids": module.get("supporting_source_ids", []),
                "preserve_existing_content": True,
                "preserve_existing_images": True,
                "article_mutation_authorized": False,
                "expected_reader_value": module.get("expected_reader_value", ""),
            }
        )
    return rows


def _write_publication_modules(output: Path, modules: list[dict[str, Any]]) -> None:
    lines = ["# Publication modules", ""]
    if not modules:
        lines.append("No module passed final overclaim review.")
    for module in modules:
        lines.extend(
            [
                f"## {module.get('proposed_heading', 'Editorial enrichment')}",
                "",
                f"- Target section: {module.get('target_section', '')}",
                f"- Reader question: {module.get('reader_question', '')}",
                f"- Supporting source IDs: {', '.join(str(item) for item in module.get('supporting_source_ids', []))}",
                f"- Synthesis type: {module.get('synthesis_type', InformationClass.EDITORIAL_INFERENCE.value)}",
                f"- Confidence: {module.get('confidence', '')}",
                "",
            ]
        )
        paragraphs = module.get("paragraphs", [])
        if isinstance(paragraphs, str):
            paragraphs = [paragraphs]
        for paragraph in paragraphs if isinstance(paragraphs, list) else []:
            lines.extend([normalize_text(str(paragraph)), ""])
        lines.extend(
            [
                f"Limitation: {module.get('limitation', '')}",
                "",
                f"Internal-link opportunity: {module.get('internal_link_opportunity', '')}",
                "",
                f"Image opportunity: {module.get('image_opportunity', '')}",
                "",
                f"Expected reader value: {module.get('expected_reader_value', '')}",
                "",
            ]
        )
    write_text(output / "publication-modules.md", "\n".join(lines).rstrip() + "\n")


def _write_section_copy(output: Path, modules: list[dict[str, Any]]) -> None:
    lines = ["# Section enrichment copy", ""]
    for module in modules:
        lines.extend([f"## {module.get('target_section', 'Editorial enrichment')}", ""])
        paragraphs = module.get("paragraphs", [])
        if isinstance(paragraphs, str):
            paragraphs = [paragraphs]
        for paragraph in paragraphs if isinstance(paragraphs, list) else []:
            lines.extend([normalize_text(str(paragraph)), ""])
    if not modules:
        lines.append("No publication-ready copy passed final overclaim review.")
    write_text(output / "section-enrichment-copy.md", "\n".join(lines).rstrip() + "\n")
