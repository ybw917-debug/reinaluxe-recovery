from __future__ import annotations

import csv
import json
import socket
from pathlib import Path
from typing import Any

import pytest

from reinaluxe_recovery.community import (
    CommunityWorkflowError,
    apply_community_decisions,
    build_community_knowledge_base,
    export_community_review,
    import_community_manifest,
)
from reinaluxe_recovery.community.normalization import (
    normalize_claim_text,
    normalize_language,
    normalize_platform_name,
    normalize_text,
    normalize_url,
)


def _source(source_id: str = "source-1", **updates: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "source_record_id": source_id,
        "platform": " Owner ",
        "community_or_channel": "offline notes",
        "source_type": "owner_note",
        "source_url": "HTTPS://EXAMPLE.COM:443/post?b=2&a=1#reply",
        "retrieved_at": "2026-07-15T10:00:00+08:00",
        "language": "en_us",
        "raw_excerpt": "  A sample\nexcerpt. ",
        "source_scope": "example model",
        "copyright_retention_mode": "necessary_excerpt_only",
        "visibility": "internal_only",
        "metadata": {},
    }
    value.update(updates)
    return value


def _claim(claim_id: str | None = "claim-1", **updates: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "claim_text": "Model A uses polished brass hardware.",
        "claim_type": "hardware_claim",
        "brand": "Example",
        "model": "Model A",
        "source_record_ids": ["source-1"],
        "evidence_record_ids": [],
        "extraction_method": "manual",
        "sensitivity": "internal",
        "proposed_publication_scope": "internal_only",
    }
    if claim_id is not None:
        value["claim_id"] = claim_id
    value.update(updates)
    return value


def _manifest(**updates: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema_version": "1.0",
        "import_batch_id": "batch-001",
        "created_at": "2026-07-15T10:00:00+08:00",
        "default_encoding": "utf-8",
        "sources": [_source()],
        "candidate_claims": [_claim()],
        "evidence_records": [],
        "metadata": {"fixture": True},
    }
    value.update(updates)
    return value


def _write_manifest(root: Path, value: dict[str, Any]) -> Path:
    path = root / "manifest.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _import(root: Path, value: dict[str, Any] | None = None) -> Path:
    output = root / "imports"
    import_community_manifest(_write_manifest(root, value or _manifest()), output)
    return output


def _edit_review(path: Path, decisions: dict[str, dict[str, str]]) -> None:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    for row in rows:
        row.update(decisions.get(row["claim_id"], {}))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def test_normalization_utilities_are_deterministic() -> None:
    assert normalize_text("Ａ  bag\n") == "A bag"
    assert normalize_claim_text(" Brass  HARDWARE ") == "brass hardware"
    assert normalize_platform_name("First-Party") == "first_party"
    assert normalize_language("zh_cn") == "zh-CN"
    assert (
        normalize_url("HTTPS://EXAMPLE.COM:443/x?b=2&a=1#z")
        == "https://example.com/x?a=1&b=2"
    )


def test_valid_import_is_offline_stable_and_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def deny_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket, "create_connection", deny_network)
    manifest = _manifest(
        sources=[
            {
                key: value
                for key, value in _source().items()
                if key != "source_record_id"
            }
        ],
        candidate_claims=[],
    )
    path = _write_manifest(tmp_path, manifest)
    output = tmp_path / "output"
    first = import_community_manifest(path, output)
    first_bytes = {item.name: item.read_bytes() for item in output.iterdir()}
    second = import_community_manifest(path, output)
    assert first == second
    assert first_bytes == {item.name: item.read_bytes() for item in output.iterdir()}
    source = _jsonl(output / "normalized-source-records.jsonl")[0]
    assert source["source_record_id"].startswith("src_")
    assert source["source_url"] == "https://example.com/post?a=1&b=2"
    assert first["offline_only"] is True


def test_stable_generated_claim_id_on_rerun(tmp_path: Path) -> None:
    output = _import(tmp_path, _manifest(candidate_claims=[_claim(None)]))
    first = (output / "candidate-claims.jsonl").read_bytes()
    import_community_manifest(tmp_path / "manifest.json", output)
    assert first == (output / "candidate-claims.jsonl").read_bytes()
    assert _jsonl(output / "candidate-claims.jsonl")[0]["claim_id"].startswith("clm_")


@pytest.mark.parametrize(
    "change",
    [
        {"schema_version": "2.0"},
        {"unexpected": True},
        {"candidate_claims": [_claim(claim_type="invented")]},
    ],
)
def test_invalid_schema_is_rejected(tmp_path: Path, change: dict[str, Any]) -> None:
    with pytest.raises(CommunityWorkflowError):
        import_community_manifest(
            _write_manifest(tmp_path, _manifest(**change)), tmp_path / "out"
        )
    assert not (tmp_path / "out").exists()


def test_path_traversal_is_rejected(tmp_path: Path) -> None:
    source = _source()
    source.pop("raw_excerpt")
    source.update(
        {"input_file": "../private.txt", "input_format": "text", "encoding": "utf-8"}
    )
    with pytest.raises(CommunityWorkflowError, match="escapes"):
        import_community_manifest(
            _write_manifest(tmp_path, _manifest(sources=[source])), tmp_path / "out"
        )


def test_local_text_and_json_inputs_are_supported(tmp_path: Path) -> None:
    (tmp_path / "excerpt.txt").write_text(
        "Only the necessary excerpt.", encoding="utf-8"
    )
    claim = _claim()
    (tmp_path / "claim.json").write_text(json.dumps(claim), encoding="utf-8")
    source = _source()
    source.pop("raw_excerpt")
    source.update(
        {"input_file": "excerpt.txt", "input_format": "text", "encoding": "utf-8"}
    )
    manifest = _manifest(
        sources=[source],
        candidate_claims=[
            {"input_file": "claim.json", "input_format": "json", "encoding": "utf-8"}
        ],
    )
    output = _import(tmp_path, manifest)
    assert (
        _jsonl(output / "normalized-source-records.jsonl")[0]["raw_excerpt"]
        == "Only the necessary excerpt."
    )
    assert len(_jsonl(output / "candidate-claims.jsonl")) == 1


def test_exact_and_likely_duplicates_are_reported_without_likely_merge(
    tmp_path: Path,
) -> None:
    sources = [_source(), _source("source-duplicate")]
    claims = [
        _claim(),
        _claim("claim-exact", source_record_ids=["source-duplicate"]),
        _claim(
            "claim-likely", claim_text="Model A uses a polished brass hardware finish."
        ),
    ]
    output = _import(tmp_path, _manifest(sources=sources, candidate_claims=claims))
    warnings = json.loads((output / "import-warnings.json").read_text(encoding="utf-8"))
    assert any(item["code"] == "exact_duplicate_source" for item in warnings)
    assert any(item["code"] == "exact_duplicate_claim" for item in warnings)
    assert any(item["code"] == "likely_duplicate_claim" for item in warnings)
    assert len(_jsonl(output / "candidate-claims.jsonl")) == 2


def test_duplicate_evidence_ids_are_remapped_to_canonical_record(
    tmp_path: Path,
) -> None:
    evidence = {
        "evidence_type": "documentary_record",
        "source_record_ids": ["source-1"],
        "evidence_summary": "One sanitized record.",
        "applicable_claim_ids": ["claim-1"],
        "scope_constraints": "Example only",
        "provenance": "offline fixture",
        "collected_at": "2026-07-15T10:00:00+08:00",
        "confidentiality": "internal_only",
    }
    imported = _import(
        tmp_path,
        _manifest(
            candidate_claims=[
                _claim(evidence_record_ids=["evidence-copy"]),
            ],
            evidence_records=[
                {**evidence, "evidence_id": "evidence-canonical"},
                {**evidence, "evidence_id": "evidence-copy"},
            ],
        ),
    )
    assert len(_jsonl(imported / "evidence-records.jsonl")) == 1
    claim = _jsonl(imported / "candidate-claims.jsonl")[0]
    assert claim["evidence_record_ids"] == ["evidence-canonical"]


def test_reused_record_id_with_different_content_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(CommunityWorkflowError, match="reused for different content"):
        _import(
            tmp_path,
            _manifest(
                candidate_claims=[
                    _claim("same-id"),
                    _claim("same-id", claim_text="A different proposition."),
                ]
            ),
        )


def test_supplier_defaults_are_restricted_and_ai_claim_is_unverified(
    tmp_path: Path,
) -> None:
    source = _source(source_type="supplier_statement", visibility=None)
    claim = _claim(extraction_method="ai_assisted_unverified")
    evidence = {
        "evidence_id": "evidence-1",
        "evidence_type": "supplier_confirmation",
        "source_record_ids": ["source-1"],
        "evidence_summary": "Scoped confirmation.",
        "applicable_claim_ids": ["claim-1"],
        "scope_constraints": "Model A only",
        "provenance": {"confidential": True},
        "collected_at": "2026-07-15T10:00:00+08:00",
    }
    imported = _import(
        tmp_path,
        _manifest(
            sources=[source], candidate_claims=[claim], evidence_records=[evidence]
        ),
    )
    assert (
        _jsonl(imported / "normalized-source-records.jsonl")[0]["visibility"]
        == "restricted_supplier_evidence"
    )
    assert (
        _jsonl(imported / "evidence-records.jsonl")[0]["confidentiality"]
        == "restricted_supplier_evidence"
    )
    review = tmp_path / "review"
    export_community_review(imported, review)
    rows = json.loads((review / "claim-review-queue.json").read_text(encoding="utf-8"))
    assert rows[0]["current_support_level"] == "unsupported"
    assert rows[0]["owner_decision"] == ""
    assert rows[0]["suggested_decision"] == ""


def test_blank_decisions_remain_pending_and_invalid_decisions_fail(
    tmp_path: Path,
) -> None:
    imported = _import(tmp_path)
    review = tmp_path / "review"
    export_community_review(imported, review)
    summary = apply_community_decisions(
        review / "claim-review-queue.csv", imported, tmp_path / "pending-decisions"
    )
    assert summary["pending_count"] == 1
    assert (tmp_path / "pending-decisions" / "review-decisions.jsonl").read_text(
        encoding="utf-8"
    ) == ""
    _edit_review(
        review / "claim-review-queue.csv", {"claim-1": {"owner_decision": "invented"}}
    )
    with pytest.raises(CommunityWorkflowError):
        apply_community_decisions(
            review / "claim-review-queue.csv", imported, tmp_path / "invalid"
        )


def test_decisions_require_reviewer_and_timestamp(tmp_path: Path) -> None:
    imported = _import(tmp_path)
    review = tmp_path / "review"
    export_community_review(imported, review)
    _edit_review(
        review / "claim-review-queue.csv",
        {
            "claim-1": {
                "owner_decision": "approved",
                "owner_rationale": "Reviewed.",
                "support_level": "verified_first_party",
                "publication_status": "internal_only",
            }
        },
    )
    with pytest.raises(CommunityWorkflowError):
        apply_community_decisions(
            review / "claim-review-queue.csv", imported, tmp_path / "decisions"
        )


def test_kb_includes_only_approved_and_preserves_qualification(tmp_path: Path) -> None:
    claims = [
        _claim("approved"),
        _claim("qualified", claim_text="Model A may use coated hardware."),
        _claim("rejected", claim_text="Model A is always flawless."),
        _claim("contradicted", claim_text="Model A never uses brass."),
        _claim("stale", claim_text="Model A was available in 2020."),
    ]
    evidence = {
        "evidence_id": "reviewed-evidence",
        "evidence_type": "first_party_specimen_inspection",
        "source_record_ids": ["source-1"],
        "evidence_summary": "Sanitized specimen inspection.",
        "applicable_claim_ids": ["approved", "qualified"],
        "scope_constraints": "Inspected samples only",
        "provenance": "owner inspection record",
        "collected_at": "2026-07-15T10:00:00+08:00",
        "confidentiality": "internal_only",
    }
    imported = _import(
        tmp_path,
        _manifest(candidate_claims=claims, evidence_records=[evidence]),
    )
    review = tmp_path / "review"
    export_community_review(imported, review)
    base = {
        "reviewer": "owner",
        "reviewed_at": "2026-07-15T12:00:00+08:00",
        "owner_rationale": "Reviewed against retained evidence.",
        "support_level": "verified_first_party",
        "publication_status": "internal_only",
    }
    decisions = {
        "approved": {**base, "owner_decision": "approved"},
        "qualified": {
            **base,
            "owner_decision": "approved_with_qualification",
            "required_qualification": "Applies only to inspected samples.",
        },
        "rejected": {
            **base,
            "owner_decision": "rejected",
            "publication_status": "do_not_publish",
        },
        "contradicted": {
            **base,
            "owner_decision": "contradicted",
            "support_level": "contradicted",
            "publication_status": "do_not_publish",
        },
        "stale": {
            **base,
            "owner_decision": "stale",
            "publication_status": "do_not_publish",
        },
    }
    _edit_review(review / "claim-review-queue.csv", decisions)
    decision_dir = tmp_path / "decisions"
    apply_community_decisions(review / "claim-review-queue.csv", imported, decision_dir)
    kb = tmp_path / "kb"
    summary = build_community_knowledge_base(decision_dir, kb)
    entries = _jsonl(kb / "approved-knowledge.jsonl")
    assert summary["approved_knowledge_count"] == 2
    assert {item["source_claim_id"] for item in entries} == {"approved", "qualified"}
    qualified = next(item for item in entries if item["source_claim_id"] == "qualified")
    assert qualified["required_qualification"] == "Applies only to inspected samples."
    assert "provenance" not in (kb / "approved-knowledge.csv").read_text(
        encoding="utf-8"
    )
    assert "excerpt" not in (kb / "approved-knowledge.csv").read_text(encoding="utf-8")


def test_supplier_kb_defaults_internal_without_public_summary_approval(
    tmp_path: Path,
) -> None:
    source = _source(source_type="supplier_statement", visibility=None)
    evidence = {
        "evidence_id": "supplier-evidence",
        "evidence_type": "supplier_confirmation",
        "source_record_ids": ["source-1"],
        "evidence_summary": "Confidential scoped support.",
        "applicable_claim_ids": ["claim-1"],
        "scope_constraints": "Model A only",
        "provenance": {"supplier_identity": "must-not-export"},
        "collected_at": "2026-07-15T10:00:00+08:00",
    }
    imported = _import(
        tmp_path, _manifest(sources=[source], evidence_records=[evidence])
    )
    review = tmp_path / "review"
    export_community_review(imported, review)
    _edit_review(
        review / "claim-review-queue.csv",
        {
            "claim-1": {
                "owner_decision": "approved",
                "owner_rationale": "Scoped review.",
                "reviewer": "owner",
                "reviewed_at": "2026-07-15T12:00:00+08:00",
                "support_level": "supplier_verified_scoped",
                "publication_status": "pending",
            }
        },
    )
    decision_dir = tmp_path / "decisions"
    apply_community_decisions(review / "claim-review-queue.csv", imported, decision_dir)
    kb = tmp_path / "kb"
    build_community_knowledge_base(decision_dir, kb)
    entry = _jsonl(kb / "approved-knowledge.jsonl")[0]
    assert entry["publication_status"] == "internal_only"
    all_output = "".join(path.read_text(encoding="utf-8") for path in kb.iterdir())
    assert "must-not-export" not in all_output

    _edit_review(
        review / "claim-review-queue.csv",
        {"claim-1": {"publication_status": "publishable"}},
    )
    publishable_decisions = tmp_path / "publishable-decisions"
    apply_community_decisions(
        review / "claim-review-queue.csv", imported, publishable_decisions
    )
    publishable_kb = tmp_path / "publishable-kb"
    build_community_knowledge_base(publishable_decisions, publishable_kb)
    publishable_entry = _jsonl(publishable_kb / "approved-knowledge.jsonl")[0]
    assert publishable_entry["publication_status"] == "publishable"
    publishable_output = "".join(
        path.read_text(encoding="utf-8") for path in publishable_kb.iterdir()
    )
    assert "must-not-export" not in publishable_output
