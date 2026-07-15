"""Owner opportunity review export and deterministic decision import."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from reinaluxe_recovery.community.io import (
    prepare_output,
    read_csv,
    write_csv,
    write_json,
    write_jsonl,
    write_text,
)
from reinaluxe_recovery.community.normalization import content_hash
from reinaluxe_recovery.content_ops.common import typed_jsonl
from reinaluxe_recovery.content_ops.errors import OpportunityDecisionError
from reinaluxe_recovery.domain.community import (
    ApprovedKnowledgeEntry,
    KnowledgePublicationStatus,
)
from reinaluxe_recovery.domain.content_ops import (
    ContentOpportunity,
    ContentOpportunityType,
    DraftingPriority,
    OpportunityDecisionValue,
    OpportunityReviewDecision,
    PageContextRecord,
)

REVIEW_FIELDS = [
    "opportunity_id",
    "knowledge_entry_id",
    "approved_knowledge_text",
    "knowledge_required_qualification",
    "support_level",
    "publication_status",
    "proposed_target_page",
    "page_role",
    "proposed_location",
    "opportunity_type",
    "mapping_rationale",
    "entity_matches",
    "intent_compatibility",
    "overlap_risk",
    "paired_page_dependency",
    "evidence_ids",
    "source_claim_ids",
    "owner_decision",
    "owner_rationale",
    "reviewer",
    "reviewed_at",
    "approved_target",
    "approved_type",
    "approved_location",
    "owner_required_qualification",
    "paired_page_requirement",
    "drafting_priority",
    "follow_up_required",
    "follow_up_question",
]


def export_opportunity_review(input_directory: Path, output: Path) -> dict[str, Any]:
    opportunities, knowledge, pages = _load_mapping(input_directory)
    knowledge_by_id = {item.knowledge_entry_id: item for item in knowledge}
    page_by_id = {item.page_context_id: item for item in pages}
    rows: list[dict[str, Any]] = []
    for opportunity in sorted(opportunities, key=lambda item: item.opportunity_id):
        entry_id = opportunity.knowledge_entry_ids[0]
        entry = knowledge_by_id.get(entry_id)
        if entry is None:
            raise OpportunityDecisionError(
                f"opportunity references missing knowledge entry: {entry_id}"
            )
        page = (
            page_by_id.get(opportunity.page_context_ids[0])
            if opportunity.page_context_ids
            else None
        )
        rows.append(
            {
                "opportunity_id": opportunity.opportunity_id,
                "knowledge_entry_id": entry_id,
                "approved_knowledge_text": entry.approved_claim,
                "knowledge_required_qualification": entry.required_qualification,
                "support_level": opportunity.support_level.value,
                "publication_status": opportunity.publication_status.value,
                "proposed_target_page": str(opportunity.target_page_url or ""),
                "page_role": page.final_role if page else "",
                "proposed_location": opportunity.proposed_location,
                "opportunity_type": opportunity.opportunity_type.value,
                "mapping_rationale": opportunity.mapping_reason,
                "entity_matches": opportunity.entity_match_evidence,
                "intent_compatibility": opportunity.intent_compatibility,
                "overlap_risk": opportunity.overlap_risk,
                "paired_page_dependency": [
                    str(item) for item in opportunity.paired_page_dependencies
                ],
                "evidence_ids": opportunity.evidence_ids,
                "source_claim_ids": opportunity.source_claim_ids,
                "owner_decision": "",
                "owner_rationale": "",
                "reviewer": "",
                "reviewed_at": "",
                "approved_target": "",
                "approved_type": "",
                "approved_location": "",
                "owner_required_qualification": "",
                "paired_page_requirement": "",
                "drafting_priority": "",
                "follow_up_required": "",
                "follow_up_question": "",
            }
        )
    prepare_output(output)
    write_csv(output / "opportunity-review-queue.csv", REVIEW_FIELDS, rows)
    write_json(output / "opportunity-review-queue.json", rows)
    write_text(output / "opportunity-review-guide.md", _review_guide())
    page_counts = Counter(
        row["proposed_target_page"] for row in rows if row["proposed_target_page"]
    )
    write_csv(
        output / "page-impact-summary.csv",
        ["page_url", "opportunity_count"],
        [
            {"page_url": url, "opportunity_count": count}
            for url, count in sorted(page_counts.items())
        ],
    )
    knowledge_counts = Counter(row["knowledge_entry_id"] for row in rows)
    write_csv(
        output / "knowledge-usage-summary.csv",
        ["knowledge_entry_id", "opportunity_count"],
        [
            {"knowledge_entry_id": entry_id, "opportunity_count": count}
            for entry_id, count in sorted(knowledge_counts.items())
        ],
    )
    return {"opportunity_count": len(rows), "preapproved_count": 0}


def apply_opportunity_decisions(
    review_path: Path, input_directory: Path, output: Path
) -> dict[str, Any]:
    opportunities, knowledge, pages = _load_mapping(input_directory)
    opportunity_by_id = {item.opportunity_id: item for item in opportunities}
    knowledge_by_id = {item.knowledge_entry_id: item for item in knowledge}
    page_urls = {str(item.page_url) for item in pages}
    headers, rows = read_csv(review_path)
    missing = [field for field in REVIEW_FIELDS if field not in headers]
    if missing:
        raise OpportunityDecisionError(
            f"opportunity review CSV is missing fields: {', '.join(missing)}"
        )
    decisions: dict[str, OpportunityReviewDecision] = {}
    pending: list[dict[str, str]] = []
    changed_ids: set[str] = set()
    seen: dict[str, dict[str, str]] = {}
    for row in rows:
        opportunity_id = row.get("opportunity_id", "").strip()
        opportunity = opportunity_by_id.get(opportunity_id)
        if opportunity is None:
            raise OpportunityDecisionError(
                f"review references unknown opportunity_id: {opportunity_id}"
            )
        if opportunity_id in seen and seen[opportunity_id] != row:
            raise OpportunityDecisionError(
                f"conflicting final decisions for opportunity: {opportunity_id}"
            )
        seen[opportunity_id] = row
        raw_decision = row.get("owner_decision", "").strip()
        if not raw_decision:
            pending.append(row)
            continue
        try:
            decision_value = OpportunityDecisionValue(raw_decision)
        except ValueError as error:
            raise OpportunityDecisionError(
                f"invalid opportunity decision for {opportunity_id}: {raw_decision}"
            ) from error
        entry = knowledge_by_id[opportunity.knowledge_entry_ids[0]]
        if (
            entry.publication_status is KnowledgePublicationStatus.INTERNAL_ONLY
            and decision_value
            not in {
                OpportunityDecisionValue.INTERNAL_ONLY,
                OpportunityDecisionValue.NO_ACTION,
                OpportunityDecisionValue.REJECTED,
                OpportunityDecisionValue.DEFER,
                OpportunityDecisionValue.NEEDS_MORE_EVIDENCE,
            }
        ):
            raise OpportunityDecisionError(
                "internal-only knowledge cannot be upgraded in opportunity review"
            )
        target = _optional(row.get("approved_target"))
        approved_type = _optional(row.get("approved_type"))
        approved_location = _optional(row.get("approved_location"))
        if decision_value is OpportunityDecisionValue.USE_FOR_NEW_ARTICLE:
            target = None
            approved_type = ContentOpportunityType.NEW_ARTICLE_CANDIDATE.value
        elif target is None and opportunity.target_page_url is not None:
            target = str(opportunity.target_page_url)
        if target is not None and target not in page_urls:
            raise OpportunityDecisionError(
                f"changed target is not in page context: {target}"
            )
        effective_type = approved_type or opportunity.opportunity_type.value
        try:
            parsed_type = ContentOpportunityType(effective_type)
            priority = DraftingPriority(row.get("drafting_priority", "").strip())
        except ValueError as error:
            raise OpportunityDecisionError(
                f"invalid approved type or drafting priority for {opportunity_id}"
            ) from error
        qualification = (
            _optional(row.get("owner_required_qualification"))
            or opportunity.required_qualification
        )
        payload = {
            "opportunity_id": opportunity_id,
            "decision": decision_value.value,
            "reviewer": row.get("reviewer", "").strip(),
            "reviewed_at": row.get("reviewed_at", "").strip(),
            "rationale": row.get("owner_rationale", "").strip(),
            "target_page_url": target,
            "approved_opportunity_type": parsed_type.value,
            "approved_location": approved_location or opportunity.proposed_location,
            "required_qualification": qualification,
            "paired_page_requirement": _parse_urls(
                row.get("paired_page_requirement", "")
            )
            or [str(item) for item in opportunity.paired_page_dependencies],
            "drafting_priority": priority.value,
            "follow_up_required": _parse_bool(row.get("follow_up_required", "")),
            "follow_up_question": _optional(row.get("follow_up_question")),
        }
        try:
            decision = OpportunityReviewDecision.model_validate(payload)
        except ValueError as error:
            raise OpportunityDecisionError(
                f"invalid decision for opportunity: {opportunity_id}"
            ) from error
        decisions[opportunity_id] = decision
        if (
            target
            != (
                str(opportunity.target_page_url)
                if opportunity.target_page_url is not None
                else None
            )
            or parsed_type is not opportunity.opportunity_type
            or payload["approved_location"] != opportunity.proposed_location
            or qualification != opportunity.required_qualification
        ):
            changed_ids.add(opportunity_id)

    ordered = [decisions[key] for key in sorted(decisions)]
    approved = [
        item
        for item in ordered
        if item.decision
        in {
            OpportunityDecisionValue.APPROVED,
            OpportunityDecisionValue.APPROVED_WITH_CHANGES,
        }
    ]
    prepare_output(output)
    write_jsonl(output / "opportunity-decisions.jsonl", ordered)
    write_jsonl(output / "approved-opportunities.jsonl", approved)
    write_jsonl(
        output / "changed-opportunities.jsonl",
        [item for item in ordered if item.opportunity_id in changed_ids],
    )
    _write_review_subset(
        output / "rejected-opportunities.csv",
        rows,
        decisions,
        {OpportunityDecisionValue.REJECTED, OpportunityDecisionValue.DUPLICATE},
    )
    _write_review_subset(
        output / "deferred-opportunities.csv",
        rows,
        decisions,
        {
            OpportunityDecisionValue.DEFER,
            OpportunityDecisionValue.NEEDS_MORE_EVIDENCE,
            OpportunityDecisionValue.CONFLICTS_WITH_PAGE_ROLE,
        },
    )
    write_csv(output / "pending-opportunities.csv", REVIEW_FIELDS, pending)
    write_jsonl(output / "decision-opportunities.jsonl", opportunities)
    write_jsonl(output / "decision-knowledge-index.jsonl", knowledge)
    write_jsonl(output / "decision-page-context.jsonl", pages)
    summary = {
        "schema_version": "1.0",
        "decision_count": len(ordered),
        "approved_count": len(approved),
        "changed_count": len(changed_ids),
        "pending_count": len(pending),
        "rejected_count": sum(
            item.decision is OpportunityDecisionValue.REJECTED for item in ordered
        ),
        "deferred_count": sum(
            item.decision is OpportunityDecisionValue.DEFER for item in ordered
        ),
    }
    write_json(output / "decision-summary.json", summary)
    return summary


def _load_mapping(
    directory: Path,
) -> tuple[
    list[ContentOpportunity], list[ApprovedKnowledgeEntry], list[PageContextRecord]
]:
    opportunities = typed_jsonl(
        directory / "content-opportunities.jsonl", ContentOpportunity
    )
    for opportunity in opportunities:
        payload = opportunity.model_dump(
            mode="json", exclude={"opportunity_id", "content_hash"}
        )
        if content_hash(payload) != opportunity.content_hash:
            raise OpportunityDecisionError(
                f"opportunity content hash mismatch: {opportunity.opportunity_id}"
            )
    return (
        opportunities,
        typed_jsonl(
            directory / "mapping-knowledge-index.jsonl", ApprovedKnowledgeEntry
        ),
        typed_jsonl(directory / "mapping-page-context.jsonl", PageContextRecord),
    )


def _write_review_subset(
    path: Path,
    rows: list[dict[str, str]],
    decisions: dict[str, OpportunityReviewDecision],
    selected: set[OpportunityDecisionValue],
) -> None:
    write_csv(
        path,
        REVIEW_FIELDS,
        [
            row
            for row in rows
            if row.get("opportunity_id") in decisions
            and decisions[row["opportunity_id"]].decision in selected
        ],
    )


def _parse_urls(value: str) -> list[str]:
    if not value.strip():
        return []
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return sorted(str(item).strip() for item in parsed if str(item).strip())
    except json.JSONDecodeError:
        pass
    return sorted(
        part.strip() for part in value.replace(";", "|").split("|") if part.strip()
    )


def _parse_bool(value: str) -> bool:
    normalized = value.strip().casefold()
    if normalized in {"", "false", "no", "0"}:
        return False
    if normalized in {"true", "yes", "1"}:
        return True
    raise OpportunityDecisionError("follow_up_required must be blank, true, or false")


def _optional(value: str | None) -> str | None:
    return value.strip() if value and value.strip() else None


def _review_guide() -> str:
    return """# Content opportunity review guide

Every opportunity is pending. Approved knowledge is not permission to draft or
publish. Confirm the final page role before accepting a target, preserve every
qualification, inspect overlap and paired-page dependencies, and use
`use_for_new_article` only for a distinct user question whose current-page
collision analysis is complete. Internal-only knowledge cannot be upgraded.
Blank decisions remain pending. This queue contains no replacement copy.
"""
