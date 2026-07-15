"""Owner-approved ContentChangeManifest construction and safety locking."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from reinaluxe_recovery.community.io import (
    prepare_output,
    write_csv,
    write_json,
    write_text,
)
from reinaluxe_recovery.community.normalization import content_hash, stable_id
from reinaluxe_recovery.content_ops.common import model_payload, typed_jsonl
from reinaluxe_recovery.content_ops.errors import ChangeManifestError
from reinaluxe_recovery.content_ops.page_context import (
    current_version_constraints,
    validate_page_context,
)
from reinaluxe_recovery.content_ops.snapshot import validate_snapshot
from reinaluxe_recovery.domain.community import ApprovedKnowledgeEntry
from reinaluxe_recovery.domain.content_ops import (
    ContentChangeManifest,
    ContentOpportunity,
    ContentOpportunityType,
    OpportunityDecisionValue,
    OpportunityReviewDecision,
    PageContextRecord,
)


def build_content_change_manifest(
    decisions_directory: Path,
    knowledge_snapshot: Path,
    page_context: Path,
    output: Path,
    database: Path | None = None,
) -> ContentChangeManifest:
    """Create the sole future drafting input without drafting or mutating pages."""
    knowledge_manifest = validate_snapshot(knowledge_snapshot)
    page_manifest, page_records = validate_page_context(page_context)
    decisions = typed_jsonl(
        decisions_directory / "opportunity-decisions.jsonl",
        OpportunityReviewDecision,
    )
    opportunities = typed_jsonl(
        decisions_directory / "decision-opportunities.jsonl", ContentOpportunity
    )
    knowledge = typed_jsonl(
        decisions_directory / "decision-knowledge-index.jsonl",
        ApprovedKnowledgeEntry,
    )
    decision_pages = typed_jsonl(
        decisions_directory / "decision-page-context.jsonl", PageContextRecord
    )
    if {item.page_context_id: item.context_hash for item in decision_pages} != {
        item.page_context_id: item.context_hash for item in page_records
    }:
        raise ChangeManifestError(
            "decision page context does not match supplied snapshot"
        )
    snapshot_knowledge = typed_jsonl(
        knowledge_snapshot / "approved-knowledge-snapshot.jsonl",
        ApprovedKnowledgeEntry,
    ) + typed_jsonl(
        knowledge_snapshot / "internal-only-index.jsonl", ApprovedKnowledgeEntry
    )
    if {item.knowledge_entry_id: item.content_hash for item in knowledge} != {
        item.knowledge_entry_id: item.content_hash for item in snapshot_knowledge
    }:
        raise ChangeManifestError("decision knowledge does not match supplied snapshot")

    opportunity_by_id = {item.opportunity_id: item for item in opportunities}
    knowledge_by_id = {item.knowledge_entry_id: item for item in knowledge}
    page_by_url = {str(item.page_url): item for item in page_records}
    approved = [
        item
        for item in decisions
        if item.decision
        in {
            OpportunityDecisionValue.APPROVED,
            OpportunityDecisionValue.APPROVED_WITH_CHANGES,
        }
    ]
    if not approved:
        raise ChangeManifestError("no approved opportunity decisions are available")

    affected_urls: set[str] = set()
    allowed_knowledge: set[str] = set()
    qualifications: dict[str, str] = {}
    approved_types: dict[str, ContentOpportunityType] = {}
    paired: dict[str, list[str]] = {}
    page_constraints: dict[str, dict[str, str]] = {}
    for decision in approved:
        opportunity = opportunity_by_id.get(decision.opportunity_id)
        if opportunity is None:
            raise ChangeManifestError(
                f"approved decision references missing opportunity: {decision.opportunity_id}"
            )
        for knowledge_id in opportunity.knowledge_entry_ids:
            entry = knowledge_by_id.get(knowledge_id)
            if entry is None:
                raise ChangeManifestError(
                    f"approved opportunity references missing knowledge: {knowledge_id}"
                )
            if (
                entry.stale_after is not None
                and entry.stale_after <= decision.reviewed_at
            ):
                raise ChangeManifestError(
                    f"approved knowledge is stale: {knowledge_id}"
                )
            if entry.contradicted_by_entry_ids:
                raise ChangeManifestError(
                    f"approved knowledge is contradicted: {knowledge_id}"
                )
            if entry.required_qualification:
                if decision.required_qualification != entry.required_qualification:
                    raise ChangeManifestError(
                        f"required qualification changed for knowledge: {knowledge_id}"
                    )
                qualifications[knowledge_id] = entry.required_qualification
            elif decision.required_qualification:
                qualifications[knowledge_id] = decision.required_qualification
            allowed_knowledge.add(knowledge_id)
        target = str(decision.target_page_url) if decision.target_page_url else None
        approved_type = (
            decision.approved_opportunity_type or opportunity.opportunity_type
        )
        if target:
            page = page_by_url.get(target)
            if page is None:
                raise ChangeManifestError(
                    f"approved target is missing from page context: {target}"
                )
            affected_urls.add(target)
            page_constraints[target] = {
                "page_identity_id": page.page_identity_id,
                "article_version_id": page.article_version_id,
                "page_content_hash": page.page_content_hash,
                "context_hash": page.context_hash,
            }
        elif approved_type is not ContentOpportunityType.NEW_ARTICLE_CANDIDATE:
            raise ChangeManifestError(
                f"approved existing-page opportunity has no target: {decision.opportunity_id}"
            )
        approved_types[decision.opportunity_id] = approved_type
        paired[decision.opportunity_id] = sorted(
            str(item) for item in decision.paired_page_requirement
        )

    if database is not None:
        live = current_version_constraints(database)
        for url, constraint in page_constraints.items():
            current = live.get(url)
            if current is None or (
                current["article_version_id"] != constraint["article_version_id"]
                or current["page_content_hash"] != constraint["page_content_hash"]
            ):
                raise ChangeManifestError(f"page context is stale for target: {url}")

    nonapproved_ids = {
        item.opportunity_id
        for item in decisions
        if item.decision
        not in {
            OpportunityDecisionValue.APPROVED,
            OpportunityDecisionValue.APPROVED_WITH_CHANGES,
        }
    }
    prohibited_claims = sorted(
        {
            claim_id
            for opportunity in opportunities
            if opportunity.opportunity_id in nonapproved_ids
            for claim_id in opportunity.source_claim_ids
        }
    )
    prohibited_operations = sorted(
        {
            operation
            for page in page_records
            if str(page.page_url) in affected_urls
            for operation in page.prohibited_operations
        }
    )
    created_at = max(item.reviewed_at for item in approved)
    base: dict[str, Any] = {
        "schema_version": "1.0",
        "created_at": created_at.isoformat(),
        "page_context_snapshot_id": page_manifest["page_context_snapshot_id"],
        "page_context_snapshot_hash": page_manifest["manifest_hash"],
        "knowledge_snapshot_id": knowledge_manifest.snapshot_id,
        "knowledge_snapshot_hash": knowledge_manifest.snapshot_hash,
        "approved_opportunity_ids": sorted(item.opportunity_id for item in approved),
        "affected_page_urls": sorted(affected_urls),
        "page_version_constraints": dict(sorted(page_constraints.items())),
        "allowed_knowledge_entry_ids": sorted(allowed_knowledge),
        "prohibited_claim_ids": prohibited_claims,
        "required_qualifications": dict(sorted(qualifications.items())),
        "approved_change_types": {
            key: value.value for key, value in sorted(approved_types.items())
        },
        "prohibited_operations": prohibited_operations,
        "paired_page_requirements": dict(sorted(paired.items())),
        "drafting_constraints": [
            "Use only allowed knowledge entry IDs.",
            "Preserve required qualifications verbatim.",
            "Do not expand brand, model, material, region, or temporal scope.",
            "Do not draft redirects, canonicals, merges, URL changes, or publication actions.",
            "Treat hub opportunities as summaries and routes, not ownership of all detail.",
        ],
        "validation_requirements": [
            "Revalidate every locked article version ID and content hash before drafting.",
            "Revalidate the knowledge and page-context snapshot hashes.",
            "Confirm final page role and paired-page requirements.",
            "Confirm no prohibited claim or operation appears in drafted changes.",
            "Require a separate owner approval before WordPress or publication.",
        ],
        "owner_approval": {
            "reviewers": sorted({item.reviewer for item in approved}),
            "reviewed_at": sorted({item.reviewed_at.isoformat() for item in approved}),
            "decision_ids": sorted(item.opportunity_id for item in approved),
            "drafting_authorized_by_this_command": False,
        },
    }
    digest = content_hash(base)
    manifest = ContentChangeManifest.model_validate(
        {
            **base,
            "change_manifest_id": stable_id("change", base),
            "manifest_hash": digest,
        }
    )
    prepare_output(output)
    write_json(output / "content-change-manifest.json", model_payload(manifest))
    write_csv(
        output / "affected-pages.csv",
        [
            "page_url",
            "page_identity_id",
            "article_version_id",
            "page_content_hash",
            "context_hash",
        ],
        [
            {"page_url": url, **constraint}
            for url, constraint in sorted(page_constraints.items())
        ],
    )
    usage_rows = []
    for decision in approved:
        opportunity = opportunity_by_id[decision.opportunity_id]
        for knowledge_id in opportunity.knowledge_entry_ids:
            usage_rows.append(
                {
                    "opportunity_id": decision.opportunity_id,
                    "knowledge_entry_id": knowledge_id,
                    "required_qualification": qualifications.get(knowledge_id, ""),
                    "target_page_url": str(decision.target_page_url or ""),
                    "approved_change_type": approved_types[
                        decision.opportunity_id
                    ].value,
                }
            )
    write_csv(
        output / "approved-knowledge-usage.csv",
        [
            "opportunity_id",
            "knowledge_entry_id",
            "required_qualification",
            "target_page_url",
            "approved_change_type",
        ],
        usage_rows,
    )
    write_text(
        output / "drafting-constraints.md",
        "# Drafting constraints\n\n"
        + "\n".join(f"- {item}" for item in manifest.drafting_constraints)
        + "\n",
    )
    write_text(
        output / "validation-requirements.md",
        "# Validation requirements\n\n"
        + "\n".join(f"- {item}" for item in manifest.validation_requirements)
        + "\n",
    )
    write_json(
        output / "manifest-summary.json",
        {
            "schema_version": "1.0",
            "change_manifest_id": manifest.change_manifest_id,
            "approved_opportunity_count": len(approved),
            "affected_page_count": len(affected_urls),
            "allowed_knowledge_count": len(allowed_knowledge),
            "article_copy_generated": False,
            "database_writes": 0,
        },
    )
    return manifest
