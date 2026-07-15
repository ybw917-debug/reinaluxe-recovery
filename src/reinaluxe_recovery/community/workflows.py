"""Offline import, owner review, decision, and knowledge-base workflows."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from reinaluxe_recovery.community.contracts import (
    ClaimDraft,
    CommunityImportManifest,
    EvidenceDraft,
    SourceDraft,
)
from reinaluxe_recovery.community.exceptions import (
    CommunityDecisionError,
    CommunityManifestError,
)
from reinaluxe_recovery.community.io import (
    load_jsonl,
    model_json,
    prepare_output,
    read_csv,
    read_json,
    read_local_record,
    validate_record,
    write_csv,
    write_json,
    write_jsonl,
    write_text,
)
from reinaluxe_recovery.community.normalization import (
    content_hash,
    likely_duplicate_claims,
    normalize_claim_text,
    normalize_datetime,
    normalize_language,
    normalize_platform_name,
    normalize_text,
    normalize_url,
    possible_conflicts,
    stable_id,
)
from reinaluxe_recovery.domain.community import (
    ApprovedKnowledgeEntry,
    AtomicCandidateClaim,
    ClaimDecision,
    ClaimExtractionMethod,
    ClaimReviewDecision,
    ClaimSupportLevel,
    CommunityEvidenceType,
    CommunitySourceRecord,
    CommunitySourceType,
    EvidenceConfidentiality,
    EvidenceRecord,
    KnowledgePublicationStatus,
    SourceVisibility,
)

REVIEW_FIELDS = [
    "claim_id",
    "atomic_claim_text",
    "entities_and_scope",
    "source_type",
    "source_excerpt",
    "evidence_summary",
    "evidence_type",
    "evidence_independence_count",
    "potential_duplicate_claims",
    "possible_conflicting_claims",
    "current_support_level",
    "suggested_decision",
    "owner_decision",
    "owner_rationale",
    "support_level",
    "publication_status",
    "reviewer",
    "reviewed_at",
    "approved_wording_constraint",
    "required_qualification",
    "conflicting_claim_ids",
    "follow_up_required",
    "follow_up_question",
]


def import_community_manifest(manifest_path: Path, output: Path) -> dict[str, Any]:
    """Import a strict local manifest without invoking any network capability."""
    raw = read_json(manifest_path)
    if not isinstance(raw, dict):
        raise CommunityManifestError("community manifest must be a JSON object")
    raw = dict(raw)
    if "claims" in raw and "candidate_claims" not in raw:
        raw["candidate_claims"] = raw.pop("claims")
    if "evidence" in raw and "evidence_records" not in raw:
        raw["evidence_records"] = raw.pop("evidence")
    manifest = validate_record(CommunityImportManifest, raw, "community manifest")
    assert isinstance(manifest, CommunityImportManifest)
    root = manifest_path.resolve().parent

    expanded_sources = _expand_records(
        root, manifest.sources, manifest.default_encoding
    )
    expanded_claims = _expand_records(
        root, manifest.candidate_claims, manifest.default_encoding
    )
    expanded_evidence = _expand_records(
        root, manifest.evidence_records, manifest.default_encoding
    )

    warnings: list[dict[str, Any]] = []
    try:
        sources, source_aliases = _normalize_sources(
            expanded_sources, manifest.import_batch_id, warnings
        )
        claims, claim_aliases = _normalize_claims(
            expanded_claims, source_aliases, warnings
        )
        evidence, evidence_aliases = _normalize_evidence(
            expanded_evidence, source_aliases, claim_aliases, warnings
        )
    except ValueError as error:
        raise CommunityManifestError(
            f"community normalization failed: {error}"
        ) from error
    claims = _attach_evidence_ids(claims, evidence, evidence_aliases)
    _validate_relationships(sources, claims, evidence)

    likely = likely_duplicate_claims([model_json(item) for item in claims])
    for claim_id, matches in likely.items():
        if matches:
            warnings.append(
                {
                    "code": "likely_duplicate_claim",
                    "claim_id": claim_id,
                    "matches": matches,
                }
            )

    prepare_output(output)
    write_jsonl(output / "normalized-source-records.jsonl", sources)
    write_jsonl(output / "candidate-claims.jsonl", claims)
    write_jsonl(output / "evidence-records.jsonl", evidence)
    warnings.sort(
        key=lambda item: (str(item.get("code")), str(item.get("claim_id", "")))
    )
    write_json(output / "import-warnings.json", warnings)
    summary = {
        "schema_version": "1.0",
        "import_batch_id": manifest.import_batch_id,
        "source_record_count": len(sources),
        "candidate_claim_count": len(claims),
        "evidence_record_count": len(evidence),
        "warning_count": len(warnings),
        "offline_only": True,
        "candidate_claims_are_unverified": True,
    }
    write_json(output / "import-summary.json", summary)
    return summary


def export_community_review(input_directory: Path, output: Path) -> dict[str, Any]:
    """Create a human review queue with no suggested or automatic approval."""
    sources = _load_sources(input_directory)
    claims = _load_claims(input_directory)
    evidence = _load_evidence(input_directory)
    _validate_relationships(sources, claims, evidence)
    source_by_id = {item.source_record_id: item for item in sources}
    evidence_by_claim: dict[str, list[EvidenceRecord]] = defaultdict(list)
    for item in evidence:
        for claim_id in item.applicable_claim_ids:
            evidence_by_claim[claim_id].append(item)
    claim_payloads = [model_json(item) for item in claims]
    duplicates = likely_duplicate_claims(claim_payloads)
    conflicts = possible_conflicts(claim_payloads)
    rows = [
        _review_row(
            claim,
            source_by_id,
            evidence_by_claim[claim.claim_id],
            duplicates,
            conflicts,
        )
        for claim in sorted(claims, key=lambda item: item.claim_id)
    ]
    prepare_output(output)
    write_csv(output / "claim-review-queue.csv", REVIEW_FIELDS, rows)
    write_json(output / "claim-review-queue.json", rows)
    write_text(output / "claim-review-guide.md", _review_guide())
    write_csv(
        output / "source-index.csv",
        [
            "source_record_id",
            "platform",
            "community_or_channel",
            "source_type",
            "source_url",
            "retrieved_at",
            "visibility",
            "content_hash",
        ],
        [
            model_json(item)
            for item in sorted(sources, key=lambda item: item.source_record_id)
        ],
    )
    write_csv(
        output / "evidence-index.csv",
        [
            "evidence_id",
            "evidence_type",
            "evidence_summary",
            "applicable_claim_ids",
            "source_record_ids",
            "confidentiality",
            "content_hash",
        ],
        [
            model_json(item)
            for item in sorted(evidence, key=lambda item: item.evidence_id)
        ],
    )
    return {"claim_count": len(rows), "preapproved_count": 0}


def apply_community_decisions(
    review_path: Path, input_directory: Path, output: Path
) -> dict[str, Any]:
    """Validate owner decisions while preserving pending and rejected claims."""
    sources = _load_sources(input_directory)
    claims = _load_claims(input_directory)
    evidence = _load_evidence(input_directory)
    _validate_relationships(sources, claims, evidence)
    claim_by_id = {item.claim_id: item for item in claims}
    headers, rows = read_csv(review_path)
    missing = [field for field in REVIEW_FIELDS if field not in headers]
    if missing:
        raise CommunityDecisionError(
            f"review CSV is missing required fields: {', '.join(missing)}"
        )
    decisions: dict[str, ClaimReviewDecision] = {}
    pending: list[dict[str, str]] = []
    seen_rows: dict[str, dict[str, str]] = {}
    for row in rows:
        claim_id = row.get("claim_id", "").strip()
        if claim_id not in claim_by_id:
            raise CommunityDecisionError(
                f"review references unknown claim_id: {claim_id}"
            )
        if claim_id in seen_rows and seen_rows[claim_id] != row:
            raise CommunityDecisionError(
                f"conflicting review rows for claim_id: {claim_id}"
            )
        seen_rows[claim_id] = row
        decision_value = row.get("owner_decision", "").strip()
        if not decision_value:
            pending.append(row)
            continue
        payload = {
            "claim_id": claim_id,
            "decision": decision_value,
            "reviewer": row.get("reviewer", "").strip(),
            "reviewed_at": row.get("reviewed_at", "").strip(),
            "rationale": row.get("owner_rationale", "").strip(),
            "support_level": row.get("support_level", "").strip(),
            "publication_status": row.get("publication_status", "").strip(),
            "approved_wording_constraint": _optional(
                row.get("approved_wording_constraint")
            ),
            "required_qualification": _optional(row.get("required_qualification")),
            "conflicting_claim_ids": _split_ids(row.get("conflicting_claim_ids", "")),
            "follow_up_required": _parse_bool(row.get("follow_up_required", "")),
            "follow_up_question": _optional(row.get("follow_up_question")),
        }
        decision = validate_record(
            ClaimReviewDecision, payload, f"decision for {claim_id}"
        )
        assert isinstance(decision, ClaimReviewDecision)
        unknown_conflicts = set(decision.conflicting_claim_ids) - set(claim_by_id)
        if unknown_conflicts:
            raise CommunityDecisionError(
                f"decision for {claim_id} references unknown conflicting claim IDs"
            )
        decisions[claim_id] = decision
    prepare_output(output)
    ordered = [decisions[key] for key in sorted(decisions)]
    write_jsonl(output / "review-decisions.jsonl", ordered)
    write_csv(output / "pending-claims.csv", REVIEW_FIELDS, pending)
    _write_decision_subset(
        output / "rejected-claims.csv",
        rows,
        decisions,
        {ClaimDecision.REJECTED, ClaimDecision.DUPLICATE, ClaimDecision.OUT_OF_SCOPE},
    )
    _write_decision_subset(
        output / "contradicted-claims.csv",
        rows,
        decisions,
        {ClaimDecision.CONTRADICTED},
    )
    write_jsonl(output / "decision-source-records.jsonl", sources)
    write_jsonl(output / "decision-candidate-claims.jsonl", claims)
    write_jsonl(output / "decision-evidence-records.jsonl", evidence)
    summary = {
        "schema_version": "1.0",
        "decision_count": len(ordered),
        "pending_count": len(pending),
        "approved_count": sum(
            item.decision is ClaimDecision.APPROVED for item in ordered
        ),
        "qualified_count": sum(
            item.decision is ClaimDecision.APPROVED_WITH_QUALIFICATION
            for item in ordered
        ),
        "rejected_count": sum(
            item.decision is ClaimDecision.REJECTED for item in ordered
        ),
        "contradicted_count": sum(
            item.decision is ClaimDecision.CONTRADICTED for item in ordered
        ),
    }
    write_json(output / "decision-summary.json", summary)
    return summary


def build_community_knowledge_base(
    input_directory: Path, output: Path
) -> dict[str, Any]:
    """Build approved entries only, retaining qualifications and confidentiality."""
    decisions = [
        item
        for item in load_jsonl(
            input_directory / "review-decisions.jsonl", ClaimReviewDecision
        )
        if isinstance(item, ClaimReviewDecision)
    ]
    claims = [
        item
        for item in load_jsonl(
            input_directory / "decision-candidate-claims.jsonl", AtomicCandidateClaim
        )
        if isinstance(item, AtomicCandidateClaim)
    ]
    evidence = [
        item
        for item in load_jsonl(
            input_directory / "decision-evidence-records.jsonl", EvidenceRecord
        )
        if isinstance(item, EvidenceRecord)
    ]
    sources = [
        item
        for item in load_jsonl(
            input_directory / "decision-source-records.jsonl", CommunitySourceRecord
        )
        if isinstance(item, CommunitySourceRecord)
    ]
    _validate_relationships(sources, claims, evidence)
    claim_by_id = {item.claim_id: item for item in claims}
    evidence_by_id = {item.evidence_id: item for item in evidence}
    entries: list[ApprovedKnowledgeEntry] = []
    for decision in sorted(decisions, key=lambda item: item.claim_id):
        if decision.decision not in {
            ClaimDecision.APPROVED,
            ClaimDecision.APPROVED_WITH_QUALIFICATION,
        }:
            continue
        claim = claim_by_id.get(decision.claim_id)
        if claim is None:
            raise CommunityDecisionError(
                f"approved decision references missing claim: {decision.claim_id}"
            )
        if not claim.evidence_record_ids:
            raise CommunityDecisionError(
                f"approved claim has no linked evidence: {decision.claim_id}"
            )
        relevant_evidence = [
            evidence_by_id[item]
            for item in claim.evidence_record_ids
            if item in evidence_by_id
        ]
        publication = decision.publication_status
        has_supplier = any(
            item.evidence_type is CommunityEvidenceType.SUPPLIER_CONFIRMATION
            for item in relevant_evidence
        )
        if has_supplier and publication not in {
            KnowledgePublicationStatus.PUBLISHABLE,
            KnowledgePublicationStatus.PUBLISHABLE_WITH_ATTRIBUTION,
        }:
            publication = KnowledgePublicationStatus.INTERNAL_ONLY
        entry_payload = {
            "source_claim_id": claim.claim_id,
            "approved_claim": decision.approved_wording_constraint or claim.claim_text,
            "required_qualification": decision.required_qualification,
            "scope": _scope_text(claim),
            "brand": claim.brand,
            "model": claim.model,
            "variant": claim.variant,
            "material": claim.material,
            "applicable_time_range": {
                "valid_from": claim.valid_from,
                "valid_until": claim.valid_until,
            },
            "support_level": decision.support_level,
            "publication_status": publication,
            "evidence_ids": sorted(claim.evidence_record_ids),
            "source_record_ids": sorted(claim.source_record_ids),
            "reviewed_by": decision.reviewer,
            "reviewed_at": decision.reviewed_at,
            "supersedes_entry_ids": [],
            "contradicted_by_entry_ids": [],
            "stale_after": claim.valid_until,
            "sensitivity": claim.sensitivity,
        }
        hash_payload = _json_safe(entry_payload)
        digest = content_hash(hash_payload)
        validated_entry = validate_record(
            ApprovedKnowledgeEntry,
            {
                "knowledge_entry_id": stable_id("kb", hash_payload),
                "content_hash": digest,
                **entry_payload,
            },
            f"approved knowledge entry for {claim.claim_id}",
        )
        assert isinstance(validated_entry, ApprovedKnowledgeEntry)
        entry = validated_entry
        entries.append(entry)
    prepare_output(output)
    write_jsonl(output / "approved-knowledge.jsonl", entries)
    fields = [
        "knowledge_entry_id",
        "source_claim_id",
        "approved_claim",
        "required_qualification",
        "scope",
        "brand",
        "model",
        "variant",
        "material",
        "applicable_time_range",
        "support_level",
        "publication_status",
        "evidence_ids",
        "source_record_ids",
        "reviewed_by",
        "reviewed_at",
        "stale_after",
        "sensitivity",
        "content_hash",
    ]
    rows = [model_json(item) for item in entries]
    write_csv(output / "approved-knowledge.csv", fields, rows)
    write_csv(
        output / "internal-only-knowledge.csv",
        fields,
        [
            row
            for row in rows
            if row["publication_status"]
            in {
                KnowledgePublicationStatus.INTERNAL_ONLY.value,
                KnowledgePublicationStatus.DO_NOT_PUBLISH.value,
            }
        ],
    )
    write_csv(
        output / "qualified-knowledge.csv",
        fields,
        [row for row in rows if row.get("required_qualification")],
    )
    summary = {
        "schema_version": "1.0",
        "approved_knowledge_count": len(entries),
        "internal_only_count": sum(
            item.publication_status
            in {
                KnowledgePublicationStatus.INTERNAL_ONLY,
                KnowledgePublicationStatus.DO_NOT_PUBLISH,
            }
            for item in entries
        ),
        "qualified_count": sum(bool(item.required_qualification) for item in entries),
        "excluded_decision_count": len(decisions) - len(entries),
        "public_exports_include_confidential_provenance": False,
    }
    write_json(output / "knowledge-summary.json", summary)
    return summary


def _expand_records(
    root: Path, records: list[dict[str, Any]], encoding: str
) -> list[dict[str, Any]]:
    expanded: list[dict[str, Any]] = []
    for record in records:
        expanded.extend(read_local_record(root, record, encoding))
    return expanded


def _normalize_sources(
    records: list[dict[str, Any]], batch_id: str, warnings: list[dict[str, Any]]
) -> tuple[list[CommunitySourceRecord], dict[str, str]]:
    output: list[CommunitySourceRecord] = []
    by_hash: dict[str, CommunitySourceRecord] = {}
    hashes_by_id: dict[str, str] = {}
    aliases: dict[str, str] = {}
    for index, raw in enumerate(records):
        draft = validate_record(SourceDraft, raw, f"source record {index + 1}")
        assert isinstance(draft, SourceDraft)
        visibility = draft.visibility or (
            SourceVisibility.RESTRICTED_SUPPLIER_EVIDENCE
            if draft.source_type is CommunitySourceType.SUPPLIER_STATEMENT
            else SourceVisibility.PUBLIC_SOURCE
        )
        payload = {
            "schema_version": draft.schema_version,
            "platform": normalize_platform_name(draft.platform),
            "community_or_channel": normalize_text(draft.community_or_channel),
            "source_type": draft.source_type.value,
            "source_url": normalize_url(draft.source_url) if draft.source_url else None,
            "source_title": normalize_text(draft.source_title)
            if draft.source_title
            else None,
            "published_at": normalize_datetime(draft.published_at)
            if draft.published_at
            else None,
            "retrieved_at": normalize_datetime(draft.retrieved_at),
            "language": normalize_language(draft.language),
            "author_alias": normalize_text(draft.author_alias)
            if draft.author_alias
            else None,
            "author_identifier_hash": draft.author_identifier_hash,
            "raw_excerpt": normalize_text(draft.raw_excerpt),
            "source_summary": normalize_text(draft.source_summary)
            if draft.source_summary
            else None,
            "source_scope": normalize_text(draft.source_scope),
            "copyright_retention_mode": normalize_text(draft.copyright_retention_mode),
            "visibility": visibility.value,
            "metadata": draft.metadata,
        }
        digest = content_hash(payload)
        record_id = draft.source_record_id or stable_id("src", payload)
        if draft.import_batch_id and draft.import_batch_id != batch_id:
            raise CommunityManifestError(
                f"source record {index + 1} import_batch_id does not match manifest"
            )
        if draft.content_hash and draft.content_hash != digest:
            raise CommunityManifestError(
                f"source record {index + 1} content_hash does not match normalized content"
            )
        if record_id in hashes_by_id and hashes_by_id[record_id] != digest:
            raise CommunityManifestError(
                f"source_record_id is reused for different content: {record_id}"
            )
        hashes_by_id[record_id] = digest
        if digest in by_hash:
            canonical = by_hash[digest]
            aliases[record_id] = canonical.source_record_id
            warnings.append(
                {
                    "code": "exact_duplicate_source",
                    "source_record_id": record_id,
                    "matches": canonical.source_record_id,
                }
            )
            continue
        validated_source = validate_record(
            CommunitySourceRecord,
            {
                "source_record_id": record_id,
                "import_batch_id": draft.import_batch_id or batch_id,
                "content_hash": digest,
                **payload,
            },
            f"normalized source record {index + 1}",
        )
        assert isinstance(validated_source, CommunitySourceRecord)
        item = validated_source
        by_hash[digest] = item
        aliases[record_id] = record_id
        output.append(item)
    return sorted(output, key=lambda item: item.source_record_id), aliases


def _normalize_claims(
    records: list[dict[str, Any]],
    source_aliases: dict[str, str],
    warnings: list[dict[str, Any]],
) -> tuple[list[AtomicCandidateClaim], dict[str, str]]:
    output: list[AtomicCandidateClaim] = []
    by_hash: dict[str, AtomicCandidateClaim] = {}
    hashes_by_id: dict[str, str] = {}
    aliases: dict[str, str] = {}
    for index, raw in enumerate(records):
        draft = validate_record(ClaimDraft, raw, f"candidate claim {index + 1}")
        assert isinstance(draft, ClaimDraft)
        source_ids = sorted(
            {source_aliases.get(item, item) for item in draft.source_record_ids}
        )
        normalized = normalize_claim_text(draft.claim_text)
        if (
            draft.normalized_claim_text
            and normalize_claim_text(draft.normalized_claim_text) != normalized
        ):
            raise CommunityManifestError(
                f"candidate claim {index + 1} normalized_claim_text does not match claim_text"
            )
        identity = {
            "normalized_claim_text": normalized,
            "claim_type": draft.claim_type.value,
            "brand": _normalized_optional(draft.brand),
            "product_category": _normalized_optional(draft.product_category),
            "model": _normalized_optional(draft.model),
            "variant": _normalized_optional(draft.variant),
            "material": _normalized_optional(draft.material),
            "hardware": _normalized_optional(draft.hardware),
            "factory_or_batch_label": _normalized_optional(
                draft.factory_or_batch_label
            ),
            "market_or_region": _normalized_optional(draft.market_or_region),
            "valid_from": normalize_datetime(draft.valid_from)
            if draft.valid_from
            else None,
            "valid_until": normalize_datetime(draft.valid_until)
            if draft.valid_until
            else None,
            "sensitivity": normalize_text(draft.sensitivity),
            "proposed_publication_scope": normalize_text(
                draft.proposed_publication_scope
            ),
        }
        digest = content_hash(identity)
        claim_id = draft.claim_id or stable_id("clm", identity)
        if draft.content_hash and draft.content_hash != digest:
            raise CommunityManifestError(
                f"candidate claim {index + 1} content_hash does not match normalized content"
            )
        if claim_id in hashes_by_id and hashes_by_id[claim_id] != digest:
            raise CommunityManifestError(
                f"claim_id is reused for different content: {claim_id}"
            )
        hashes_by_id[claim_id] = digest
        if digest in by_hash:
            existing = by_hash[digest]
            aliases[claim_id] = existing.claim_id
            merged = existing.model_copy(
                update={
                    "source_record_ids": sorted(
                        set(existing.source_record_ids) | set(source_ids)
                    ),
                    "evidence_record_ids": sorted(
                        set(existing.evidence_record_ids)
                        | set(draft.evidence_record_ids)
                    ),
                }
            )
            by_hash[digest] = merged
            output[output.index(existing)] = merged
            warnings.append(
                {
                    "code": "exact_duplicate_claim",
                    "claim_id": claim_id,
                    "matches": existing.claim_id,
                }
            )
            continue
        validated_claim = validate_record(
            AtomicCandidateClaim,
            {
                "claim_id": claim_id,
                "claim_text": normalize_text(draft.claim_text),
                "normalized_claim_text": normalized,
                "source_record_ids": source_ids,
                "evidence_record_ids": sorted(set(draft.evidence_record_ids)),
                "content_hash": digest,
                **{
                    key: value
                    for key, value in identity.items()
                    if key not in {"normalized_claim_text", "valid_from", "valid_until"}
                },
                "valid_from": draft.valid_from,
                "valid_until": draft.valid_until,
                "extraction_method": draft.extraction_method,
                "extraction_notes": _normalized_optional(draft.extraction_notes),
            },
            f"normalized candidate claim {index + 1}",
        )
        assert isinstance(validated_claim, AtomicCandidateClaim)
        item = validated_claim
        aliases[claim_id] = claim_id
        by_hash[digest] = item
        output.append(item)
    return sorted(output, key=lambda item: item.claim_id), aliases


def _normalize_evidence(
    records: list[dict[str, Any]],
    source_aliases: dict[str, str],
    claim_aliases: dict[str, str],
    warnings: list[dict[str, Any]],
) -> tuple[list[EvidenceRecord], dict[str, str]]:
    output: list[EvidenceRecord] = []
    by_hash: dict[str, EvidenceRecord] = {}
    hashes_by_id: dict[str, str] = {}
    aliases: dict[str, str] = {}
    for index, raw in enumerate(records):
        draft = validate_record(EvidenceDraft, raw, f"evidence record {index + 1}")
        assert isinstance(draft, EvidenceDraft)
        confidentiality = draft.confidentiality or (
            EvidenceConfidentiality.RESTRICTED_SUPPLIER_EVIDENCE
            if draft.evidence_type is CommunityEvidenceType.SUPPLIER_CONFIRMATION
            else EvidenceConfidentiality.INTERNAL_ONLY
        )
        payload = {
            "evidence_type": draft.evidence_type.value,
            "source_record_ids": sorted(
                {source_aliases.get(item, item) for item in draft.source_record_ids}
            ),
            "evidence_summary": normalize_text(draft.evidence_summary),
            "applicable_claim_ids": sorted(
                {claim_aliases.get(item, item) for item in draft.applicable_claim_ids}
            ),
            "scope_constraints": normalize_text(draft.scope_constraints),
            "provenance": draft.provenance
            if isinstance(draft.provenance, dict)
            else normalize_text(draft.provenance),
            "collected_at": normalize_datetime(draft.collected_at),
            "valid_from": normalize_datetime(draft.valid_from)
            if draft.valid_from
            else None,
            "valid_until": normalize_datetime(draft.valid_until)
            if draft.valid_until
            else None,
            "reviewer_notes": _normalized_optional(draft.reviewer_notes),
            "confidentiality": confidentiality.value,
        }
        digest = content_hash(payload)
        evidence_id = draft.evidence_id or stable_id("evd", payload)
        if draft.content_hash and draft.content_hash != digest:
            raise CommunityManifestError(
                f"evidence record {index + 1} content_hash does not match normalized content"
            )
        if evidence_id in hashes_by_id and hashes_by_id[evidence_id] != digest:
            raise CommunityManifestError(
                f"evidence_id is reused for different content: {evidence_id}"
            )
        hashes_by_id[evidence_id] = digest
        if digest in by_hash:
            aliases[evidence_id] = by_hash[digest].evidence_id
            warnings.append(
                {
                    "code": "exact_duplicate_evidence",
                    "evidence_id": evidence_id,
                    "matches": by_hash[digest].evidence_id,
                }
            )
            continue
        validated_evidence = validate_record(
            EvidenceRecord,
            {"evidence_id": evidence_id, "content_hash": digest, **payload},
            f"normalized evidence record {index + 1}",
        )
        assert isinstance(validated_evidence, EvidenceRecord)
        item = validated_evidence
        by_hash[digest] = item
        aliases[evidence_id] = evidence_id
        output.append(item)
    return sorted(output, key=lambda item: item.evidence_id), aliases


def _attach_evidence_ids(
    claims: list[AtomicCandidateClaim],
    evidence: list[EvidenceRecord],
    evidence_aliases: dict[str, str],
) -> list[AtomicCandidateClaim]:
    by_claim: dict[str, set[str]] = defaultdict(set)
    for item in evidence:
        for claim_id in item.applicable_claim_ids:
            by_claim[claim_id].add(item.evidence_id)
    return [
        claim.model_copy(
            update={
                "evidence_record_ids": sorted(
                    {
                        evidence_aliases.get(item, item)
                        for item in claim.evidence_record_ids
                    }
                    | by_claim[claim.claim_id]
                )
            }
        )
        for claim in claims
    ]


def _validate_relationships(
    sources: list[CommunitySourceRecord],
    claims: list[AtomicCandidateClaim],
    evidence: list[EvidenceRecord],
) -> None:
    source_ids = {item.source_record_id for item in sources}
    claim_ids = {item.claim_id for item in claims}
    evidence_ids = {item.evidence_id for item in evidence}
    for claim in claims:
        unknown_sources = set(claim.source_record_ids) - source_ids
        unknown_evidence = set(claim.evidence_record_ids) - evidence_ids
        if unknown_sources or unknown_evidence:
            raise CommunityManifestError(
                f"claim {claim.claim_id} contains unknown source/evidence IDs"
            )
    for item in evidence:
        if (
            set(item.source_record_ids) - source_ids
            or set(item.applicable_claim_ids) - claim_ids
        ):
            raise CommunityManifestError(
                f"evidence {item.evidence_id} contains unknown source/claim IDs"
            )


def _review_row(
    claim: AtomicCandidateClaim,
    source_by_id: dict[str, CommunitySourceRecord],
    evidence: list[EvidenceRecord],
    duplicates: dict[str, list[dict[str, Any]]],
    conflicts: dict[str, list[str]],
) -> dict[str, Any]:
    sources = [source_by_id[item] for item in claim.source_record_ids]
    return {
        "claim_id": claim.claim_id,
        "atomic_claim_text": claim.claim_text,
        "entities_and_scope": _scope_text(claim),
        "source_type": sorted({item.source_type.value for item in sources}),
        "source_excerpt": [item.raw_excerpt for item in sources],
        "evidence_summary": [item.evidence_summary for item in evidence],
        "evidence_type": sorted({item.evidence_type.value for item in evidence}),
        "evidence_independence_count": len(
            {source for item in evidence for source in item.source_record_ids}
        ),
        "potential_duplicate_claims": duplicates.get(claim.claim_id, []),
        "possible_conflicting_claims": conflicts.get(claim.claim_id, []),
        "current_support_level": _support_level(claim, evidence).value,
        "suggested_decision": "",
        "owner_decision": "",
        "owner_rationale": "",
        "support_level": "",
        "publication_status": "",
        "reviewer": "",
        "reviewed_at": "",
        "approved_wording_constraint": "",
        "required_qualification": "",
        "conflicting_claim_ids": "",
        "follow_up_required": "",
        "follow_up_question": "",
    }


def _support_level(
    claim: AtomicCandidateClaim, evidence: list[EvidenceRecord]
) -> ClaimSupportLevel:
    if claim.extraction_method is ClaimExtractionMethod.AI_ASSISTED_UNVERIFIED:
        return ClaimSupportLevel.UNSUPPORTED
    types = {item.evidence_type for item in evidence}
    source_count = len(
        {source for item in evidence for source in item.source_record_ids}
    )
    if CommunityEvidenceType.OFFICIAL_PRIMARY_SOURCE in types:
        return ClaimSupportLevel.VERIFIED_PRIMARY
    if types & {
        CommunityEvidenceType.FIRST_PARTY_SPECIMEN_INSPECTION,
        CommunityEvidenceType.FIRST_PARTY_MEASUREMENT,
        CommunityEvidenceType.FIRST_PARTY_LONG_TERM_USE,
    }:
        return ClaimSupportLevel.VERIFIED_FIRST_PARTY
    if CommunityEvidenceType.SUPPLIER_CONFIRMATION in types:
        return ClaimSupportLevel.SUPPLIER_VERIFIED_SCOPED
    if (
        CommunityEvidenceType.INDEPENDENT_COMMUNITY_CORROBORATION in types
        and source_count >= 2
    ):
        return ClaimSupportLevel.CORROBORATED_MULTI_SOURCE
    if types & {
        CommunityEvidenceType.SINGLE_COMMUNITY_REPORT,
        CommunityEvidenceType.INDEPENDENT_COMMUNITY_CORROBORATION,
    }:
        return ClaimSupportLevel.SINGLE_SOURCE_ANECDOTE
    if CommunityEvidenceType.EDITORIAL_INFERENCE in types:
        return ClaimSupportLevel.EDITORIAL_INFERENCE
    return ClaimSupportLevel.UNSUPPORTED


def _scope_text(claim: AtomicCandidateClaim) -> str:
    values = []
    for field in (
        "brand",
        "product_category",
        "model",
        "variant",
        "material",
        "hardware",
        "factory_or_batch_label",
        "market_or_region",
    ):
        value = getattr(claim, field)
        if value:
            values.append(f"{field}={value}")
    if claim.valid_from:
        values.append(f"valid_from={normalize_datetime(claim.valid_from)}")
    if claim.valid_until:
        values.append(f"valid_until={normalize_datetime(claim.valid_until)}")
    return "; ".join(values) or "scope not further specified"


def _load_sources(path: Path) -> list[CommunitySourceRecord]:
    return [
        item
        for item in load_jsonl(
            path / "normalized-source-records.jsonl", CommunitySourceRecord
        )
        if isinstance(item, CommunitySourceRecord)
    ]


def _load_claims(path: Path) -> list[AtomicCandidateClaim]:
    return [
        item
        for item in load_jsonl(path / "candidate-claims.jsonl", AtomicCandidateClaim)
        if isinstance(item, AtomicCandidateClaim)
    ]


def _load_evidence(path: Path) -> list[EvidenceRecord]:
    return [
        item
        for item in load_jsonl(path / "evidence-records.jsonl", EvidenceRecord)
        if isinstance(item, EvidenceRecord)
    ]


def _review_guide() -> str:
    return """# Community claim review guide

Every row is an unverified candidate, not a fact. Read the retained source excerpt,
scope, dates, evidence type, independence count, duplicate hints, and conflict hints.
Leave `owner_decision` blank to keep a claim pending. A non-blank decision requires
reviewer, timezone-aware reviewed_at, rationale, support_level, and publication_status.
Use `approved_with_qualification` only with a required qualification. Never copy
confidential provenance into public wording. No decision publishes content.
"""


def _write_decision_subset(
    path: Path,
    rows: list[dict[str, str]],
    decisions: dict[str, ClaimReviewDecision],
    selected: set[ClaimDecision],
) -> None:
    write_csv(
        path,
        REVIEW_FIELDS,
        [
            row
            for row in rows
            if row.get("claim_id") in decisions
            and decisions[row["claim_id"]].decision in selected
        ],
    )


def _parse_bool(value: str) -> bool:
    normalized = value.strip().casefold()
    if normalized in {"", "false", "no", "0"}:
        return False
    if normalized in {"true", "yes", "1"}:
        return True
    raise CommunityDecisionError("follow_up_required must be blank, true, or false")


def _split_ids(value: str) -> list[str]:
    if not value.strip():
        return []
    return sorted(
        {part.strip() for part in value.replace(";", "|").split("|") if part.strip()}
    )


def _optional(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    return normalize_text(value)


def _normalized_optional(value: str | None) -> str | None:
    return normalize_text(value) if value else None


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if hasattr(value, "value"):
        return value.value
    if hasattr(value, "isoformat"):
        return normalize_datetime(value)
    return value
