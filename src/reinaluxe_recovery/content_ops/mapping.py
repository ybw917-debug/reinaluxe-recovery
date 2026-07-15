"""Transparent deterministic approved-knowledge opportunity mapping."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any

from reinaluxe_recovery.community.io import (
    prepare_output,
    write_csv,
    write_json,
    write_jsonl,
    write_text,
)
from reinaluxe_recovery.community.normalization import (
    content_hash,
    normalize_text,
    stable_id,
)
from reinaluxe_recovery.content_ops.common import model_payload, typed_jsonl
from reinaluxe_recovery.content_ops.errors import OpportunityError
from reinaluxe_recovery.content_ops.page_context import validate_page_context
from reinaluxe_recovery.content_ops.snapshot import validate_snapshot
from reinaluxe_recovery.domain.community import ApprovedKnowledgeEntry
from reinaluxe_recovery.domain.content_ops import (
    ContentOpportunity,
    ContentOpportunityType,
    OpportunityConfidence,
    PageContextRecord,
)

_TEMPORAL_RE = re.compile(r"\b20\d{2}\b|\b(?:annual|forecast|trend|current)\b", re.I)
_AUTH_TERMS = (
    "authentic",
    "authentication",
    "counterfeit",
    "fake",
    "date code",
    "serial",
)
_BUYING_TERMS = (
    "buyer",
    "buying",
    "quality tier",
    "seller",
    "factory",
    "price",
    "availability",
)
_STYLING_TERMS = ("styling", "outfit", "wardrobe", "occasion", "what to wear")
_CORRECTION_TERMS = (
    "correction:",
    "incorrect",
    "not reliable",
    "does not prove",
    "should not",
)


def map_content_opportunities(
    knowledge_snapshot: Path, page_context: Path, output: Path
) -> dict[str, Any]:
    """Map with ordered exact signals and documented role compatibility only."""
    knowledge_manifest = validate_snapshot(knowledge_snapshot)
    page_manifest, pages = validate_page_context(page_context)
    publishable = typed_jsonl(
        knowledge_snapshot / "approved-knowledge-snapshot.jsonl",
        ApprovedKnowledgeEntry,
    )
    internal = typed_jsonl(
        knowledge_snapshot / "internal-only-index.jsonl", ApprovedKnowledgeEntry
    )
    opportunities: list[ContentOpportunity] = []
    for entry in publishable:
        opportunities.extend(_map_publishable(entry, pages))
    for entry in internal:
        opportunities.append(_internal_opportunity(entry))
    opportunities.sort(key=lambda item: item.opportunity_id)
    if len({item.opportunity_id for item in opportunities}) != len(opportunities):
        raise OpportunityError(
            "deterministic mapping produced duplicate opportunity IDs"
        )

    prepare_output(output)
    write_jsonl(output / "content-opportunities.jsonl", opportunities)
    rows = [model_payload(item) for item in opportunities]
    fields = list(rows[0]) if rows else list(ContentOpportunity.model_fields)
    write_csv(output / "content-opportunities.csv", fields, rows)
    _write_subset(
        output / "new-article-candidates.csv",
        fields,
        rows,
        {ContentOpportunityType.NEW_ARTICLE_CANDIDATE.value},
    )
    existing_types = {
        item.value
        for item in ContentOpportunityType
        if item
        not in {
            ContentOpportunityType.NEW_ARTICLE_CANDIDATE,
            ContentOpportunityType.INTERNAL_ONLY_RESEARCH,
            ContentOpportunityType.NO_ACTION,
        }
    }
    _write_subset(
        output / "existing-page-opportunities.csv", fields, rows, existing_types
    )
    _write_subset(
        output / "internal-only-opportunities.csv",
        fields,
        rows,
        {ContentOpportunityType.INTERNAL_ONLY_RESEARCH.value},
    )
    _write_subset(
        output / "no-action-opportunities.csv",
        fields,
        rows,
        {ContentOpportunityType.NO_ACTION.value},
    )
    write_jsonl(output / "mapping-knowledge-index.jsonl", [*publishable, *internal])
    write_jsonl(output / "mapping-page-context.jsonl", pages)
    summary = {
        "schema_version": "1.0",
        "knowledge_snapshot_id": knowledge_manifest.snapshot_id,
        "page_context_snapshot_id": page_manifest["page_context_snapshot_id"],
        "knowledge_entry_count": len(publishable) + len(internal),
        "opportunity_count": len(opportunities),
        "existing_page_count": sum(
            bool(item.target_page_url) for item in opportunities
        ),
        "new_article_candidate_count": sum(
            item.opportunity_type is ContentOpportunityType.NEW_ARTICLE_CANDIDATE
            for item in opportunities
        ),
        "internal_only_count": sum(
            item.opportunity_type is ContentOpportunityType.INTERNAL_ONLY_RESEARCH
            for item in opportunities
        ),
        "no_action_count": sum(
            item.opportunity_type is ContentOpportunityType.NO_ACTION
            for item in opportunities
        ),
        "preapproved_count": 0,
        "drafted_copy": False,
    }
    write_json(output / "mapping-summary.json", summary)
    write_text(output / "mapping-explanations.md", _mapping_explanations())
    return summary


def _map_publishable(
    entry: ApprovedKnowledgeEntry, pages: list[PageContextRecord]
) -> list[ContentOpportunity]:
    text = _fold(f"{entry.approved_claim} {entry.scope}")
    temporal = bool(_TEMPORAL_RE.search(text))
    time_range = entry.applicable_time_range
    if temporal and time_range.valid_from is None and time_range.valid_until is None:
        return [
            _terminal_opportunity(
                entry,
                ContentOpportunityType.NO_ACTION,
                "Temporal or forecast knowledge lacks a bounded valid time range.",
                ["temporal_scope_missing"],
            )
        ]
    auth = any(term in text for term in _AUTH_TERMS)
    buying = any(term in text for term in _BUYING_TERMS)
    styling = any(term in text for term in _STYLING_TERMS)
    exact_model = [
        page
        for page in pages
        if entry.model
        and _model_match(entry.model, page)
        and _role_compatible(page, auth=auth, buying=buying, styling=styling)
    ]
    if entry.model and not exact_model:
        return [_new_article_opportunity(entry, pages, auth, buying, styling)]

    candidates = exact_model or [
        page
        for page in pages
        if _entity_match(entry, page)
        and _role_compatible(page, auth=auth, buying=buying, styling=styling)
    ]
    if not candidates:
        return [
            _terminal_opportunity(
                entry,
                ContentOpportunityType.NO_ACTION,
                "No existing page has both an exact entity signal and compatible final role.",
                ["no_compatible_page_role"],
            )
        ]
    if temporal and not entry.model:
        dated_candidates = [
            page for page in candidates if _temporal_page_match(entry, page)
        ]
        if not dated_candidates:
            return [
                _terminal_opportunity(
                    entry,
                    ContentOpportunityType.NO_ACTION,
                    "No compatible existing page has a matching dated scope.",
                    ["temporal_page_scope_mismatch"],
                )
            ]
        candidates = dated_candidates
    candidates = sorted(
        candidates,
        key=lambda page: (_candidate_rank(entry, page), str(page.page_url)),
    )
    best = candidates[0]
    opportunity_type = _opportunity_type(entry, best)
    ambiguous = [
        page
        for page in candidates[1:]
        if _candidate_rank(entry, page) == _candidate_rank(entry, best)
    ]
    conflicts = ["ambiguous_exact_mapping"] if ambiguous else []
    detail = _page_opportunity(
        entry,
        best,
        opportunity_type,
        candidates,
        conflicts,
        paired=[best.hub_url] if best.hub_url else [],
        reason_prefix=(
            "Exact normalized model match selected the narrowest compatible page"
            if entry.model
            else "Exact entity match and final page role selected the existing owner"
        ),
    )
    output = [detail]
    if entry.model and best.hub_url:
        hub = next((page for page in pages if page.page_url == best.hub_url), None)
        if hub and _role_compatible(hub, auth=auth, buying=buying, styling=styling):
            output.append(
                _page_opportunity(
                    entry,
                    hub,
                    ContentOpportunityType.ADD_SUPPORTING_SECTION,
                    [hub],
                    ["hub_summary_only"],
                    paired=[best.page_url],
                    reason_prefix=(
                        "Hub receives only a scoped overview and route; the exact-model "
                        "supporting page retains detail ownership"
                    ),
                )
            )
    return output


def _page_opportunity(
    entry: ApprovedKnowledgeEntry,
    page: PageContextRecord,
    opportunity_type: ContentOpportunityType,
    candidates: list[PageContextRecord],
    conflicts: list[str],
    paired: list[Any],
    reason_prefix: str,
) -> ContentOpportunity:
    evidence = _match_evidence(entry, page)
    compatibility = [
        f"final_role:{page.final_role}",
        f"primary_intent:{page.primary_intent}",
    ]
    overlap = sorted(
        {str(url) for url in page.closest_overlap_urls}
        | {
            str(item.page_url)
            for item in candidates[1:]
            if item.content_cluster == page.content_cluster
        }
    )
    location = _location(opportunity_type, entry)
    reason = (
        f"{reason_prefix}: {page.final_role}. Signals: {', '.join(evidence)}. "
        "The mapping does not authorize wording or publication."
    )
    payload = {
        "schema_version": "1.0",
        "knowledge_entry_ids": [entry.knowledge_entry_id],
        "page_context_ids": [page.page_context_id],
        "opportunity_type": opportunity_type.value,
        "target_page_url": str(page.page_url),
        "proposed_new_article_topic": None,
        "proposed_location": location,
        "user_question": _user_question(entry),
        "mapping_reason": reason,
        "entity_match_evidence": evidence,
        "intent_compatibility": compatibility,
        "support_level": entry.support_level.value,
        "publication_status": entry.publication_status.value,
        "required_qualification": entry.required_qualification,
        "temporal_scope": entry.applicable_time_range.model_dump(mode="json"),
        "conflict_flags": conflicts,
        "overlap_risk": overlap,
        "paired_page_dependencies": sorted(str(item) for item in paired),
        "evidence_ids": sorted(entry.evidence_ids),
        "source_claim_ids": [entry.source_claim_id],
        "confidence": (
            OpportunityConfidence.LOW.value
            if conflicts
            else OpportunityConfidence.HIGH.value
            if entry.model and any(item.startswith("model:") for item in evidence)
            else OpportunityConfidence.MEDIUM.value
        ),
        "owner_decision_status": "pending",
    }
    digest = content_hash(payload)
    return ContentOpportunity.model_validate(
        {
            **payload,
            "opportunity_id": stable_id(
                "opp",
                {
                    "knowledge": entry.knowledge_entry_id,
                    "target": str(page.page_url),
                    "type": opportunity_type.value,
                    "location": location,
                },
            ),
            "content_hash": digest,
        }
    )


def _new_article_opportunity(
    entry: ApprovedKnowledgeEntry,
    pages: list[PageContextRecord],
    auth: bool,
    buying: bool,
    styling: bool,
) -> ContentOpportunity:
    brand_pages = [page for page in pages if _brand_match(entry, page)]
    collision_urls = sorted(str(page.page_url) for page in brand_pages)
    question = _user_question(entry)
    cluster = (
        brand_pages[0].content_cluster if brand_pages else (entry.brand or "Unassigned")
    )
    reason = (
        f"The narrow model {entry.model!r} has no exact owner in the 25-page matrix. "
        f"Existing {entry.brand or 'related'} pages were retained as collision checks, "
        f"but none has that model scope. Likely cluster: {cluster}. Evidence level: "
        f"{entry.support_level.value}. Temporal durability: "
        f"{entry.applicable_time_range.model_dump(mode='json')}."
    )
    flags = []
    if auth and buying:
        flags.append("mixed_authentication_and_buying_intent")
    if styling:
        flags.append("styling_requires_genuine_next_task_review")
    payload = {
        "schema_version": "1.0",
        "knowledge_entry_ids": [entry.knowledge_entry_id],
        "page_context_ids": [],
        "opportunity_type": ContentOpportunityType.NEW_ARTICLE_CANDIDATE.value,
        "target_page_url": None,
        "proposed_new_article_topic": question,
        "proposed_location": f"candidate cluster: {cluster}",
        "user_question": question,
        "mapping_reason": reason,
        "entity_match_evidence": [f"brand:{entry.brand}", f"model:{entry.model}"],
        "intent_compatibility": ["distinct_user_question_requires_owner_review"],
        "support_level": entry.support_level.value,
        "publication_status": entry.publication_status.value,
        "required_qualification": entry.required_qualification,
        "temporal_scope": entry.applicable_time_range.model_dump(mode="json"),
        "conflict_flags": flags,
        "overlap_risk": collision_urls,
        "paired_page_dependencies": [],
        "evidence_ids": sorted(entry.evidence_ids),
        "source_claim_ids": [entry.source_claim_id],
        "confidence": OpportunityConfidence.LOW.value,
        "owner_decision_status": "pending",
    }
    return _finalize(payload, entry.knowledge_entry_id, "new", question)


def _internal_opportunity(entry: ApprovedKnowledgeEntry) -> ContentOpportunity:
    return _terminal_opportunity(
        entry,
        ContentOpportunityType.INTERNAL_ONLY_RESEARCH,
        "Knowledge is internal-only and cannot be upgraded by opportunity mapping.",
        ["internal_only_publication_boundary"],
    )


def _terminal_opportunity(
    entry: ApprovedKnowledgeEntry,
    opportunity_type: ContentOpportunityType,
    reason: str,
    flags: list[str],
) -> ContentOpportunity:
    payload = {
        "schema_version": "1.0",
        "knowledge_entry_ids": [entry.knowledge_entry_id],
        "page_context_ids": [],
        "opportunity_type": opportunity_type.value,
        "target_page_url": None,
        "proposed_new_article_topic": None,
        "proposed_location": "not applicable",
        "user_question": _user_question(entry),
        "mapping_reason": reason,
        "entity_match_evidence": [
            value
            for value in (
                f"brand:{entry.brand}" if entry.brand else None,
                f"model:{entry.model}" if entry.model else None,
            )
            if value
        ],
        "intent_compatibility": ["human_review_required"],
        "support_level": entry.support_level.value,
        "publication_status": entry.publication_status.value,
        "required_qualification": entry.required_qualification,
        "temporal_scope": entry.applicable_time_range.model_dump(mode="json"),
        "conflict_flags": flags,
        "overlap_risk": [],
        "paired_page_dependencies": [],
        "evidence_ids": sorted(entry.evidence_ids),
        "source_claim_ids": [entry.source_claim_id],
        "confidence": OpportunityConfidence.LOW.value,
        "owner_decision_status": "pending",
    }
    return _finalize(payload, entry.knowledge_entry_id, opportunity_type.value, reason)


def _finalize(
    payload: dict[str, Any], knowledge_id: str, target: str, location: str
) -> ContentOpportunity:
    return ContentOpportunity.model_validate(
        {
            **payload,
            "opportunity_id": stable_id(
                "opp",
                {"knowledge": knowledge_id, "target": target, "location": location},
            ),
            "content_hash": content_hash(payload),
        }
    )


def _entity_match(entry: ApprovedKnowledgeEntry, page: PageContextRecord) -> bool:
    return _brand_match(entry, page) or bool(
        entry.material and _fold(entry.material) in _fold(_page_text(page))
    )


def _brand_match(entry: ApprovedKnowledgeEntry, page: PageContextRecord) -> bool:
    return bool(entry.brand and page.brand and _fold(entry.brand) == _fold(page.brand))


def _model_match(model: str, page: PageContextRecord) -> bool:
    folded = _fold(model)
    return folded in {_fold(item) for item in page.models} or folded in _fold(
        _page_text(page)
    )


def _role_compatible(
    page: PageContextRecord, *, auth: bool, buying: bool, styling: bool
) -> bool:
    role = _fold(
        f"{page.final_role} {page.primary_intent} {' '.join(page.secondary_intents)}"
    )
    is_auth = "authentic" in role or "fake" in role or "verification" in role
    if auth and not is_auth:
        return False
    if buying and is_auth and not auth:
        return False
    if styling and not any(term in role for term in _STYLING_TERMS):
        return False
    return True


def _candidate_rank(
    entry: ApprovedKnowledgeEntry, page: PageContextRecord
) -> tuple[int, int, int]:
    model_rank = 0 if entry.model and _model_match(entry.model, page) else 1
    material_rank = (
        0 if entry.material and _fold(entry.material) in _fold(_page_text(page)) else 1
    )
    hub_rank = 1 if "hub" in page.final_role.casefold() else 0
    return model_rank, material_rank, hub_rank


def _temporal_page_match(
    entry: ApprovedKnowledgeEntry, page: PageContextRecord
) -> bool:
    years = {
        value.year
        for value in (
            entry.applicable_time_range.valid_from,
            entry.applicable_time_range.valid_until,
        )
        if value is not None
    }
    page_text = _fold(f"{_page_text(page)} {page.freshness_status}")
    return bool(years and any(str(year) in page_text for year in years))


def _match_evidence(
    entry: ApprovedKnowledgeEntry, page: PageContextRecord
) -> list[str]:
    values: list[str] = []
    if _brand_match(entry, page):
        values.append(f"brand:{entry.brand}")
    if entry.model and _model_match(entry.model, page):
        values.append(f"model:{entry.model}")
    if entry.material and _fold(entry.material) in _fold(_page_text(page)):
        values.append(f"material:{entry.material}")
    values.append(f"cluster:{page.content_cluster}")
    return values


def _opportunity_type(
    entry: ApprovedKnowledgeEntry, page: PageContextRecord
) -> ContentOpportunityType:
    text = _fold(entry.approved_claim)
    if any(term in text for term in _CORRECTION_TERMS):
        return ContentOpportunityType.CORRECT_EXISTING_CLAIM
    if entry.required_qualification:
        return ContentOpportunityType.QUALIFY_EXISTING_CLAIM
    if page.factual_blockers:
        return ContentOpportunityType.EVIDENCE_ENRICHMENT
    if "faq" in text or text.endswith("?"):
        return ContentOpportunityType.ADD_FAQ
    return ContentOpportunityType.ADD_SUPPORTING_SECTION


def _location(
    opportunity_type: ContentOpportunityType, entry: ApprovedKnowledgeEntry
) -> str:
    if opportunity_type is ContentOpportunityType.ADD_FAQ:
        return "FAQ review candidate"
    if opportunity_type in {
        ContentOpportunityType.CORRECT_EXISTING_CLAIM,
        ContentOpportunityType.QUALIFY_EXISTING_CLAIM,
    }:
        return "existing claim location to be owner-confirmed"
    subject = entry.model or entry.material or entry.brand or "scoped evidence"
    return f"supporting section review: {subject}"


def _user_question(entry: ApprovedKnowledgeEntry) -> str:
    subject = entry.model or entry.material or entry.brand or "this evidence"
    return f"What should a reader understand about {subject} within the approved scope?"


def _page_text(page: PageContextRecord) -> str:
    return " ".join(
        [
            str(page.page_url),
            page.current_title,
            page.current_h1,
            page.final_role,
            page.primary_intent,
            *page.secondary_intents,
            *page.models,
            *page.materials,
        ]
    )


def _fold(value: str) -> str:
    return normalize_text(
        "".join(
            character
            for character in unicodedata.normalize("NFKD", value).casefold()
            if not unicodedata.combining(character)
        )
    )


def _write_subset(
    path: Path,
    fields: list[str],
    rows: list[dict[str, Any]],
    selected: set[str],
) -> None:
    write_csv(
        path, fields, [row for row in rows if row["opportunity_type"] in selected]
    )


def _mapping_explanations() -> str:
    return """# Deterministic opportunity mapping explanations

Signals are ordered, not opaquely weighted: exact model, exact material, exact
brand, then final-role and intent compatibility. Exact model pages outrank hubs.
When a model detail page belongs to a compatible hub, the detail stays on the
supporting page and the hub receives only an overview-and-route candidate.

Authentication knowledge is filtered to authentication roles. Commercial or
tier knowledge is filtered away from authentication-only roles. Styling maps
only to an explicit styling next task. Temporal/forecast knowledge without a
valid time range produces no action. Internal-only knowledge produces internal
research only. A narrow model with no exact owner may become a new-article
candidate with collision URLs and evidence/temporal notes. Every result remains
pending owner review and contains no drafted article copy.
"""
