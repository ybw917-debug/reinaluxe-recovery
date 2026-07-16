"""Article understanding and deterministic multi-lane query planning."""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from reinaluxe_recovery.community.normalization import (
    content_hash,
    normalize_text,
    stable_id,
)
from reinaluxe_recovery.research.contracts import (
    ArticleAnalysis,
    ArticleResearchRequest,
    ContentProductionMode,
    ExistingArticleImage,
    ExistingArticleSection,
    ResearchPlan,
    ResearchQuery,
    ResearchQuestion,
    ResearchRequest,
    SourceLane,
)
from reinaluxe_recovery.research.errors import ResearchArtifactError

_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_FIRST_HAND = re.compile(
    r"\b(?:we|our|i)\s+(?:tested|compared|reviewed|observed|photographed|measured|bought)\b",
    re.IGNORECASE,
)
_FIRST_PERSON = re.compile(r"\b(?:I|we|my|our)\b", re.IGNORECASE)
_EVIDENCE_PENDING = re.compile(
    r"\b(?:always|never|guaranteed|identical|authentic|proves?|all sellers?|industry standard)\b",
    re.IGNORECASE,
)

_LANE_TERMS = {
    SourceLane.COMMUNITY_REDDIT: "site:reddit.com",
    SourceLane.COMMUNITY_FORUMS: "forum OR community discussion",
    SourceLane.PRIMARY_OFFICIAL: "official primary source",
    SourceLane.EXPERT_EDITORIAL: "expert analysis methodology",
    SourceLane.COMMERCIAL_OBSERVATION: "retailer listing observed price specifications",
    SourceLane.VISUAL_IMAGE: "photos images comparison",
}
_EVIDENCE_TYPE = {
    SourceLane.COMMUNITY_REDDIT: "public first-hand community experience or disagreement",
    SourceLane.COMMUNITY_FORUMS: "public specialist discussion or first-hand experience",
    SourceLane.PRIMARY_OFFICIAL: "definition, specification, policy, or primary factual record",
    SourceLane.EXPERT_EDITORIAL: "attributed expert method, context, or critical analysis",
    SourceLane.COMMERCIAL_OBSERVATION: "scoped commercial observation, not independent proof",
    SourceLane.VISUAL_IMAGE: "source-linked image metadata and limitations",
}

type Prompt = tuple[str, str | None, str]


def analyze_article(request: ArticleResearchRequest) -> ArticleAnalysis:
    """Read an owner-provided article artifact or current version without writes."""
    article: dict[str, Any] = {}
    if request.article_source_path is not None:
        article = _read_article_path(request.article_source_path)
    elif request.production_database_path is not None:
        article = _read_article_database(request)
    headings, paragraphs, images, links = _article_components(article)
    existing_sections, existing_images = _existing_structure(article, request)
    title = _text(article.get("title"))
    h1 = next((heading for level, heading in headings if level == 1), title)
    heading_text = [heading for _, heading in headings]
    claims = [
        sentence
        for paragraph in paragraphs
        for sentence in _sentences(paragraph)
        if len(sentence.split()) >= 5
    ]
    first_hand = [claim for claim in claims if _FIRST_HAND.search(claim)]
    unsupported = [claim for claim in claims if _EVIDENCE_PENDING.search(claim)]
    missing_questions = list(request.research_questions)
    if not any(
        "mean" in item.casefold() or "what is" in item.casefold()
        for item in heading_text
    ):
        missing_questions.append(
            "What do the key terms mean, and where does usage disagree?"
        )
    if request.image_research_required and not images:
        missing_questions.append(
            "Which source-linked visuals could illustrate the topic and their limits?"
        )
    if unsupported:
        missing_questions.append(
            "Which existing claims need corroboration, qualification, or contradiction handling?"
        )
    missing_questions = sorted(set(missing_questions))
    gaps: dict[str, list[str]] = {}
    if unsupported:
        gaps[SourceLane.PRIMARY_OFFICIAL.value] = unsupported
        gaps[SourceLane.EXPERT_EDITORIAL.value] = unsupported
    if claims:
        gaps[SourceLane.COMMUNITY_REDDIT.value] = [
            "first-hand experiences that test existing article claims"
        ]
        gaps[SourceLane.COMMUNITY_FORUMS.value] = [
            "specialist discussion and disagreement"
        ]
    if request.image_research_required:
        gaps[SourceLane.VISUAL_IMAGE.value] = [
            "source-linked images with permission and evidence limitations"
        ]
    return ArticleAnalysis(
        title=title,
        h1=h1,
        headings=heading_text,
        existing_claims=claims,
        images=images,
        internal_links=links,
        page_role=_infer_page_role(title, h1, heading_text),
        first_hand_material=first_hand,
        unsupported_claims=unsupported,
        missing_user_questions=missing_questions,
        evidence_gaps_by_lane=gaps,
        existing_sections=existing_sections,
        existing_images=existing_images,
    )


def build_research_plan(request: ResearchRequest) -> ResearchPlan:
    """Build stable questions and a quota-respecting multi-source query plan."""
    hashed_request = request.with_request_hash()
    article_analysis = (
        analyze_article(hashed_request)
        if isinstance(hashed_request, ArticleResearchRequest)
        else None
    )
    reusable_topic_ids = _reusable_topic_ids(
        hashed_request.research_database_path, hashed_request.topic_ids
    )
    primary_prompts: list[Prompt] = []
    for value in hashed_request.research_questions:
        primary_prompts.append((value, None, "owner-defined research question"))
    for family in hashed_request.query_families:
        primary_prompts.append(
            (_question_for_family(family), None, f"query family: {family}")
        )
    topic_prompts: list[Prompt] = [
        (
            f"What current evidence defines, limits, or refreshes topic {topic_id}?",
            None,
            "approved topic scope",
        )
        for topic_id in hashed_request.topic_ids
    ]
    missing_prompts: list[Prompt] = []
    unsupported_prompts: list[Prompt] = []
    heading_prompts: list[Prompt] = []
    existing_claim_prompts: list[Prompt] = []
    if article_analysis:
        missing_prompts = [
            (value, None, "missing user question identified from article")
            for value in article_analysis.missing_user_questions
        ]
        unsupported_prompts = [
            (
                f"What evidence supports, limits, or contradicts: {value}",
                _section_for_claim(value, article_analysis.headings),
                "existing evidence-pending claim",
            )
            for value in article_analysis.unsupported_claims[:8]
        ]
        heading_prompts = [
            (
                f"What evidence would strengthen the section '{heading}'?",
                heading,
                "article heading",
            )
            for heading in article_analysis.headings[:8]
        ]
        unsupported = set(article_analysis.unsupported_claims)
        existing_claim_prompts = [
            (
                f"Which public sources support or limit the existing claim: {value}",
                _section_for_claim(value, article_analysis.headings),
                "existing article claim",
            )
            for value in [
                claim
                for claim in article_analysis.existing_claims
                if claim not in unsupported
            ][:8]
        ]
    secondary_groups: list[list[Prompt]] = [
        topic_prompts,
        missing_prompts,
        unsupported_prompts,
        heading_prompts,
        existing_claim_prompts,
        _knowledge_questions(hashed_request.approved_knowledge_paths),
        _contradiction_questions(hashed_request.prior_research_paths),
    ]
    prompts = list(primary_prompts)
    maximum_group_length = max((len(group) for group in secondary_groups), default=0)
    for index in range(maximum_group_length):
        for group in secondary_groups:
            if index < len(group):
                prompts.append(group[index])
    unique: dict[str, tuple[str | None, str]] = {}
    for question, section, rationale in prompts:
        normalized = normalize_text(question)
        unique.setdefault(normalized.casefold(), (section, rationale))
    questions = [
        ResearchQuestion(
            question_id=stable_id(
                "rq", {"research_id": hashed_request.research_id, "question": question}
            ),
            question=question,
            rationale=section_rationale[1],
            topic_ids=hashed_request.topic_ids,
            target_article_section=section_rationale[0],
            evidence_gap=section_rationale[1],
            priority=index + 1,
        )
        for index, (question, section_rationale) in enumerate(unique.items())
    ]
    if not questions:
        questions = [
            ResearchQuestion(
                question_id=stable_id("rq", hashed_request.owner_objective),
                question=hashed_request.owner_objective,
                rationale="owner objective",
                topic_ids=hashed_request.topic_ids,
            )
        ]
    queries = _allocate_queries(hashed_request, questions, reusable_topic_ids)
    base = {
        "research_id": hashed_request.research_id,
        "request_hash": hashed_request.request_hash,
        "mode": hashed_request.mode,
        "provider": hashed_request.provider,
        "target_article_url": hashed_request.target_article_url,
        "questions": questions,
        "queries": queries,
        "source_lane_policies": sorted(
            hashed_request.source_lane_priorities,
            key=lambda item: (item.priority, item.source_lane.value),
        ),
        "article_analysis": article_analysis,
        "maximum_search_calls": hashed_request.maximum_search_calls,
        "maximum_sources": hashed_request.maximum_sources,
        "maximum_image_candidates": hashed_request.maximum_image_candidates,
        "image_research_required": hashed_request.image_research_required,
        "content_production_mode": hashed_request.content_production_mode,
        "publication_intensity": hashed_request.publication_intensity,
        "preserve_existing_images": hashed_request.preserve_existing_images,
        "preserve_distinctive_content": hashed_request.preserve_distinctive_content,
        "owner_firsthand_evidence_required": hashed_request.owner_firsthand_evidence_required,
        "maximum_new_sections": hashed_request.maximum_new_sections,
        "owner_voice_evidence": hashed_request.owner_voice_evidence,
        "distinctive_content_requirements": hashed_request.distinctive_content_requirements,
        "existing_image_requirements": hashed_request.existing_image_requirements,
        "minimum_existing_image_count": hashed_request.minimum_existing_image_count,
        "asset_root": hashed_request.asset_root,
        "asset_manifest": hashed_request.asset_manifest,
        "search_intents": hashed_request.search_intents,
        "research_database_path": hashed_request.research_database_path,
        "reusable_topic_ids": reusable_topic_ids,
    }
    draft = ResearchPlan.model_validate(base)
    plan_hash = content_hash(draft.model_dump(mode="json", exclude={"plan_hash"}))
    return draft.model_copy(update={"plan_hash": plan_hash})


def _allocate_queries(
    request: ResearchRequest,
    questions: list[ResearchQuestion],
    reusable_topic_ids: list[str],
) -> list[ResearchQuery]:
    reusable = set(reusable_topic_ids)
    eligible_questions = [
        question
        for question in questions
        if not (
            request.content_production_mode is ContentProductionMode.NEW_PAGE_BUILD
            and question.topic_ids
            and set(question.topic_ids) <= reusable
        )
    ]
    if not eligible_questions:
        return []
    policies = sorted(
        (
            policy
            for policy in request.source_lane_priorities
            if policy.enabled and policy.query_quota
        ),
        key=lambda item: (item.priority, item.source_lane.value),
    )
    remaining = {policy.source_lane: policy.query_quota for policy in policies}
    languages = [request.language, *request.alternate_languages]
    output: list[ResearchQuery] = []
    question_number = 0
    while len(output) < request.maximum_search_calls and any(remaining.values()):
        added = False
        for policy in policies:
            if (
                not remaining[policy.source_lane]
                or len(output) >= request.maximum_search_calls
            ):
                continue
            question = eligible_questions[question_number % len(eligible_questions)]
            language = languages[question_number % len(languages)]
            base_terms = " ".join([*request.brand_scope, *request.model_scope]).strip()
            lane_term = _LANE_TERMS[policy.source_lane]
            exclusions = sorted(set(request.excluded_subjects))
            exclusion_text = " ".join(f'-"{item}"' for item in exclusions)
            language_text = (
                "" if language == request.language else f" language:{language}"
            )
            search_text = normalize_text(
                f"{lane_term} {base_terms} {question.question} "
                f"{exclusion_text}{language_text}"
            )
            seed = {
                "question": question.question_id,
                "lane": policy.source_lane,
                "language": language,
                "sequence": remaining[policy.source_lane],
            }
            output.append(
                ResearchQuery(
                    query_id=stable_id("query", seed),
                    research_question_id=question.question_id,
                    source_lane=policy.source_lane,
                    search_text=search_text,
                    positive_terms=[*request.brand_scope, *request.model_scope],
                    exclusion_terms=exclusions,
                    temporal_range=request.temporal_scope,
                    brand_scope=request.brand_scope,
                    model_scope=request.model_scope,
                    target_article_section=question.target_article_section,
                    expected_evidence_type=_EVIDENCE_TYPE[policy.source_lane],
                    stopping_criteria=(
                        f"stop this lane after {policy.source_quota} accepted sources "
                        f"or {policy.query_quota} queries"
                    ),
                    language=language,
                )
            )
            remaining[policy.source_lane] -= 1
            question_number += 1
            added = True
        if not added:
            break
    if output and len({item.source_lane for item in output}) < min(2, len(policies)):
        raise ResearchArtifactError(
            "research plan did not retain configured source diversity"
        )
    return output


def _read_article_path(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as error:
        raise ResearchArtifactError(f"could not read article source: {path}") from error
    if path.suffix.casefold() in {".html", ".htm"}:
        soup = BeautifulSoup(text, "html.parser")
        return {
            "title": soup.title.get_text(" ", strip=True) if soup.title else None,
            "sections": [
                {
                    "heading": {
                        "level": int(tag.name[1]),
                        "text": tag.get_text(" ", strip=True),
                    },
                    "paragraphs": [],
                    "images": [],
                    "links": [],
                }
                for tag in soup.find_all(re.compile(r"^h[1-6]$"))
            ],
            "paragraphs": [tag.get_text(" ", strip=True) for tag in soup.find_all("p")],
            "images": [
                {"source_url": tag.get("src"), "alt_text": tag.get("alt")}
                for tag in soup.find_all("img")
                if tag.get("src")
            ],
            "links": [tag.get("href") for tag in soup.find_all("a") if tag.get("href")],
        }
    try:
        value = json.loads(text)
    except json.JSONDecodeError as error:
        raise ResearchArtifactError(
            "article source must be normalized JSON or HTML"
        ) from error
    if not isinstance(value, dict):
        raise ResearchArtifactError("normalized article source must contain an object")
    return value


def _read_article_database(request: ArticleResearchRequest) -> dict[str, Any]:
    assert request.production_database_path is not None
    resolved = request.production_database_path.resolve()
    uri = f"file:{resolved.as_posix()}?mode=ro&immutable=1"
    try:
        connection = sqlite3.connect(uri, uri=True)
        if request.article_version_id:
            row = connection.execute(
                "SELECT normalized_content_hash, normalized_article_json FROM article_versions WHERE id=?",
                (request.article_version_id,),
            ).fetchone()
        else:
            row = connection.execute(
                """SELECT a.normalized_content_hash, a.normalized_article_json
                   FROM page_identities p JOIN article_versions a
                   ON a.id=p.current_article_version_id WHERE p.canonical_url=?""",
                (str(request.target_article_url),),
            ).fetchone()
        connection.close()
    except sqlite3.Error as error:
        raise ResearchArtifactError(
            "could not read production article database"
        ) from error
    if row is None:
        raise ResearchArtifactError("target article version was not found")
    if request.article_content_hash and row[0] != request.article_content_hash:
        raise ResearchArtifactError(
            "article content hash does not match current repository version"
        )
    value = json.loads(row[1])
    if not isinstance(value, dict):
        raise ResearchArtifactError("stored normalized article is not an object")
    return value


def _article_components(
    article: Mapping[str, Any],
) -> tuple[list[tuple[int, str]], list[str], list[str], list[str]]:
    headings: list[tuple[int, str]] = []
    paragraphs: list[str] = []
    images: list[str] = []
    links: list[str] = []
    for section in article.get("sections", []) or []:
        if not isinstance(section, dict):
            continue
        heading = section.get("heading")
        if isinstance(heading, dict) and _text(heading.get("text")):
            headings.append(
                (int(heading.get("level", 2)), _text(heading["text"]) or "")
            )
        for paragraph in section.get("paragraphs", []) or []:
            value = paragraph.get("text") if isinstance(paragraph, dict) else paragraph
            if _text(value):
                paragraphs.append(_text(value) or "")
        for image in section.get("images", []) or []:
            value = image.get("source_url") if isinstance(image, dict) else image
            if _text(value):
                images.append(_text(value) or "")
        for link in section.get("links", []) or []:
            value = link.get("target_url") if isinstance(link, dict) else link
            if _text(value) and _is_internal(_text(value) or ""):
                links.append(_text(value) or "")
    for paragraph in article.get("paragraphs", []) or []:
        value = paragraph.get("text") if isinstance(paragraph, dict) else paragraph
        if _text(value):
            paragraphs.append(_text(value) or "")
    for image in article.get("images", []) or []:
        value = image.get("source_url") if isinstance(image, dict) else image
        if _text(value):
            images.append(_text(value) or "")
    for link in article.get("links", []) or []:
        value = link.get("target_url") if isinstance(link, dict) else link
        if _text(value) and _is_internal(_text(value) or ""):
            links.append(_text(value) or "")
    return headings, paragraphs, sorted(set(images)), sorted(set(links))


def _existing_structure(
    article: Mapping[str, Any], request: ArticleResearchRequest
) -> tuple[list[ExistingArticleSection], list[ExistingArticleImage]]:
    sections: list[ExistingArticleSection] = []
    images: list[ExistingArticleImage] = []
    requirements = [
        item.casefold() for item in request.distinctive_content_requirements
    ]
    raw_section_values = article.get("sections", []) or []
    raw_sections = (
        list(raw_section_values) if isinstance(raw_section_values, list) else []
    )
    root_paragraphs = article.get("paragraphs", []) or []
    root_images = article.get("images", []) or []
    root_links = article.get("links", []) or []
    article_title = _text(article.get("title"))
    if root_paragraphs or root_images or root_links:
        raw_sections.insert(
            0,
            {
                "heading": {"level": 1, "text": article_title or "Article"},
                "paragraphs": root_paragraphs,
                "images": root_images,
                "links": root_links,
            },
        )
    elif not raw_sections and article_title:
        raw_sections.append({"heading": {"level": 1, "text": article_title}})
    for order, raw_section in enumerate(raw_sections):
        if not isinstance(raw_section, dict):
            continue
        heading_value = raw_section.get("heading")
        heading = heading_value if isinstance(heading_value, dict) else {}
        heading_text = _text(heading.get("text")) or (
            _text(article.get("title")) or f"Section {order + 1}"
        )
        level = int(heading.get("level", 2))
        section_id = str(
            raw_section.get("id")
            or stable_id(
                "existing_section",
                {
                    "research_id": request.research_id,
                    "order": order,
                    "heading": heading_text,
                },
            )
        )
        paragraph_values: list[str] = []
        for paragraph in raw_section.get("paragraphs", []) or []:
            value = paragraph.get("text") if isinstance(paragraph, dict) else paragraph
            text = _text(value)
            if text:
                paragraph_values.append(text)
        section_image_ids: list[str] = []
        for image_order, raw_image in enumerate(raw_section.get("images", []) or []):
            image_value = (
                raw_image if isinstance(raw_image, dict) else {"source_url": raw_image}
            )
            source_url = _text(image_value.get("source_url"))
            if not source_url:
                continue
            image_id = str(
                image_value.get("id")
                or stable_id(
                    "existing_image",
                    {"section_id": section_id, "order": image_order, "url": source_url},
                )
            )
            section_image_ids.append(image_id)
            images.append(
                ExistingArticleImage(
                    image_id=image_id,
                    source_url=source_url,
                    section_id=section_id,
                    alt_text=_text(image_value.get("alt_text")),
                    caption=_text(image_value.get("caption")),
                    preserve=request.preserve_existing_images,
                )
            )
        internal_links: list[str] = []
        for raw_link in raw_section.get("links", []) or []:
            link_value = (
                raw_link.get("target_url") if isinstance(raw_link, dict) else raw_link
            )
            link_text = _text(link_value)
            if link_text and _is_internal(link_text):
                internal_links.append(link_text)
        first_person = [text for text in paragraph_values if _FIRST_PERSON.search(text)]
        distinctive = [
            text
            for text in paragraph_values
            if text in first_person
            or any(requirement in text.casefold() for requirement in requirements)
        ]
        sections.append(
            ExistingArticleSection(
                section_id=section_id,
                order=order,
                heading_level=level,
                heading=heading_text,
                paragraphs=paragraph_values,
                image_ids=section_image_ids,
                internal_links=sorted(set(internal_links)),
                distinctive_passages=distinctive,
                first_person_passages=first_person,
            )
        )
    return sections, images


def _reusable_topic_ids(database: Path | None, topic_ids: list[str]) -> list[str]:
    if database is None or not database.is_file() or not topic_ids:
        return []
    resolved = database.resolve()
    uri = f"file:{resolved.as_posix()}?mode=ro&immutable=1"
    try:
        with sqlite3.connect(uri, uri=True) as connection:
            rows = connection.execute(
                """SELECT tc.topic_id, COUNT(DISTINCT tc.claim_id),
                          COUNT(DISTINCT ts.source_id)
                   FROM topic_claims tc
                   LEFT JOIN topic_sources ts ON ts.topic_id=tc.topic_id
                   GROUP BY tc.topic_id"""
            ).fetchall()
    except sqlite3.Error:
        return []
    available = {
        str(topic_id) for topic_id, claims, sources in rows if claims and sources
    }
    return sorted(set(topic_ids) & available)


def _sentences(text: str) -> list[str]:
    return [normalize_text(item) for item in _SENTENCE.split(text) if item.strip()]


def _text(value: Any) -> str | None:
    return (
        normalize_text(str(value)) if value is not None and str(value).strip() else None
    )


def _is_internal(value: str) -> bool:
    return value.startswith("/") or "reinaluxe.co" in value.casefold()


def _infer_page_role(title: str | None, h1: str | None, headings: list[str]) -> str:
    composite = " ".join(item for item in [title, h1, *headings] if item).casefold()
    if "guide" in composite:
        return "guide"
    if "review" in composite:
        return "review"
    if "compare" in composite or " vs " in composite:
        return "comparison"
    return "informational article"


def _section_for_claim(claim: str, headings: list[str]) -> str | None:
    claim_terms = set(claim.casefold().split())
    scored = sorted(
        (
            (len(claim_terms & set(heading.casefold().split())), heading)
            for heading in headings
        ),
        reverse=True,
    )
    return scored[0][1] if scored and scored[0][0] else None


def _question_for_family(family: str) -> str:
    normalized = family.replace("_", " ").replace("-", " ").strip()
    return f"What evidence, limitations, and disagreements exist about {normalized}?"


def _knowledge_questions(paths: list[Path]) -> list[tuple[str, str | None, str]]:
    output: list[tuple[str, str | None, str]] = []
    for path in paths:
        if not path.exists() or not path.is_file():
            continue
        try:
            records = [
                json.loads(line)
                for line in path.read_text(encoding="utf-8-sig").splitlines()
                if line.strip()
            ]
        except (OSError, json.JSONDecodeError):
            continue
        for item in records[:8]:
            if isinstance(item, dict):
                claim = item.get("approved_claim") or item.get("claim_text")
                if claim:
                    output.append(
                        (
                            f"Does current public evidence still support: {claim}",
                            None,
                            "existing Approved Knowledge",
                        )
                    )
    return output


def _contradiction_questions(paths: list[Path]) -> list[tuple[str, str | None, str]]:
    output: list[tuple[str, str | None, str]] = []
    for directory in paths:
        path = (
            directory / "contradiction-register.csv"
            if directory.is_dir()
            else directory
        )
        if path.exists():
            output.append(
                (
                    f"Which newer evidence could scope unresolved contradictions from {path.stem}?",
                    None,
                    "known contradiction",
                )
            )
    return output


def _json_payload(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {key: _json_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_payload(item) for item in value]
    return value
