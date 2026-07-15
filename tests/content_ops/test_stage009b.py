from __future__ import annotations

import csv
import hashlib
import json
import shutil
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from reinaluxe_recovery.community import import_community_manifest
from reinaluxe_recovery.content_ops import (
    ContentOpsError,
    apply_opportunity_decisions,
    build_content_change_manifest,
    build_knowledge_snapshot,
    build_page_context,
    export_opportunity_review,
    map_content_opportunities,
)

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "stage009b"

PAGE_SPECS = [
    (
        "aaa-replica-bags-guide-for-us",
        "General replica-bag education",
        "US logistics and transaction-safety supporting guide",
        "Supporting article",
        "US buying logistics",
        "seller evaluation",
    ),
    (
        "aaa-replica-bags-guide",
        "General replica-bag education",
        "Evergreen sitewide replica-bag education hub",
        "Hub",
        "buyer education",
        "quality tiers",
    ),
    (
        "aaa-replica-reviews/best-celine-replica-bags-2025",
        "Annual brand and trend reviews",
        "Celine model-comparison page with a dated evidence frame",
        "Keep and optimize",
        "compare Celine models",
        "care",
    ),
    (
        "aaa-replica-reviews/best-selling-hermes-replica-bags-2025",
        "Hermès",
        "Dated Birkin 25 vs Kelly 28 vs Constance 18 comparison",
        "Reposition",
        "compare Birkin 25 vs Kelly 28 vs Constance 18",
        "Hermès tiers",
    ),
    (
        "aaa-replica-reviews/bottega-veneta-replica-bags-2026",
        "Annual brand and trend reviews",
        "Bottega-specific 2026 forecast and model comparison",
        "Keep and optimize",
        "Bottega forecast",
        "styling",
    ),
    (
        "aaa-replica-reviews/chanel-mini-bag-replica-vs-authentic-aaa-guide",
        "Chanel",
        "Chanel Mini Gold Ball and Pearl Crush forensic comparison",
        "Supporting article",
        "replica-versus-authentic Chanel Mini detail",
        "hardware",
    ),
    (
        "aaa-replica-reviews/chanel-replica-bag-2025-guide",
        "Chanel",
        "Classic Flap vs Chanel 22 vs Chanel 19 comparison",
        "Reposition",
        "compare Classic Flap vs Chanel 22 vs Chanel 19",
        "hardware and use case",
    ),
    (
        "aaa-replica-reviews/hermes-mini-kelly-ii-replica-review",
        "Hermès",
        "Single-product Mini Kelly II evidence-led review",
        "Supporting article",
        "evaluate Mini Kelly II specimen",
        "Epsom leather stitching",
    ),
    (
        "aaa-replica-reviews/most-popular-replica-bag-brands-2026",
        "Annual brand and trend reviews",
        "Conditional annual discovery hub",
        "Hub",
        "discover annual brands",
        "trend categories",
    ),
    (
        "aaa-replica-reviews/the-goyard-replica-bags-2026",
        "Annual brand and trend reviews",
        "Goyard 2026 model and canvas-quality comparison",
        "Keep",
        "compare Goyard models",
        "canvas craftsmanship",
    ),
    (
        "aaa-replica-reviews/the-gucci-replica-bags-2026",
        "Annual brand and trend reviews",
        "Gucci 2026 model and trend comparison",
        "Keep",
        "compare Gucci models",
        "styling",
    ),
    (
        "aaa-replica-reviews/the-row-replica-bags-2026",
        "Annual brand and trend reviews",
        "The Row Margaux and Park Tote comparison",
        "Keep",
        "compare Margaux and Park Tote",
        "leather quality",
    ),
    (
        "bag-fashion-trends/how-to-match-bags-outfits-guide",
        "Styling",
        "Standalone styling and wardrobe-use guide",
        "Keep",
        "match bags to outfits",
        "occasion and proportion",
    ),
    (
        "best-chanel-replica-bags-guide",
        "Chanel",
        "Evergreen Chanel replica-bag hub",
        "Hub",
        "Chanel buying and quality guide",
        "models leather hardware",
    ),
    (
        "best-hermes-replica-bags-guide",
        "Hermès",
        "Evergreen Hermès replica-bag hub",
        "Hub",
        "Hermès buying and craftsmanship guide",
        "models leathers tiers",
    ),
    (
        "how-to-spot-fake-bags/fake-designer-bag-authentication-guide",
        "Authentication and craftsmanship",
        "Cross-brand authentication hub",
        "Hub",
        "authentication workflow",
        "logos materials hardware stitching",
    ),
    (
        "how-to-spot-fake-bags/hermes-constance-authentication-guide",
        "Hermès",
        "Constance 18 authentication supporting guide",
        "Supporting article",
        "authenticate Constance 18",
        "Epsom leather hardware stitching",
    ),
    (
        "how-to-spot-fake-bags/how-to-chanel-authenticate",
        "Chanel",
        "Chanel authentication supporting method guide",
        "Supporting article",
        "authenticate Chanel bags",
        "serial hardware",
    ),
    (
        "how-to-spot-fake-bags/louis-vuitton-materials-guide",
        "Louis Vuitton",
        "LV Monogram canvas materials and durability reference",
        "Supporting article",
        "compare Louis Vuitton materials",
        "Monogram canvas durability",
    ),
    (
        "how-to-spot-fake-bags/luxury-bag-craftsmanship-guide",
        "Authentication and craftsmanship",
        "Bag-anatomy and craftsmanship primer",
        "Supporting article",
        "understand bag construction",
        "materials hardware stitching",
    ),
    (
        "how-to-spot-fake-bags/lv-bag-authentication-guide",
        "Louis Vuitton",
        "LV authentication hub",
        "Hub",
        "authenticate Louis Vuitton bags",
        "canvas hardware date codes",
    ),
    (
        "louis-vuitton/lv-aaa-trends-top-3-picks-2026",
        "Louis Vuitton",
        "Dated LV top-three trend supporting page",
        "Reposition",
        "2026 LV model picks",
        "basic flaw checks",
    ),
    (
        "louis-vuitton/lv-classic-bags",
        "Louis Vuitton",
        "Classic LV model decision guide",
        "Refresh",
        "Speedy Alma Neverfull choice",
        "history and use",
    ),
    (
        "louis-vuitton/modern-lv-icons-review",
        "Louis Vuitton",
        "Modern LV model decision and styling guide",
        "Keep",
        "Dauphine Multi-Pochette modern models",
        "styling",
    ),
    (
        "lv-craftsmanship-and-replica-guide",
        "Louis Vuitton",
        "LV Monogram canvas craftsmanship comparison",
        "Reposition",
        "compare canvas print craftsmanship",
        "authentication limits",
    ),
]


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _planning_fixture(root: Path) -> tuple[Path, Path, Path, Path, Path]:
    role_path = root / "role.csv"
    finding_path = root / "findings.csv"
    readiness_path = root / "readiness.csv"
    roadmap = root / "roadmap.md"
    database = root / "pages.db"
    role_fields = [
        "URL",
        "current role",
        "final role",
        "primary intent",
        "secondary intent",
        "cluster",
        "final disposition",
        "confidence",
        "closest-overlap pages",
        "planned phase",
        "approved-correction dependency",
        "freshness disposition",
        "URL action",
    ]
    role_rows: list[dict[str, str]] = []
    urls = [f"https://reinaluxe.co/{spec[0]}/" for spec in PAGE_SPECS]
    for index, (slug, cluster, role, disposition, primary, secondary) in enumerate(
        PAGE_SPECS
    ):
        overlaps = ""
        if cluster == "Chanel":
            overlaps = "best-chanel-replica-bags-guide; chanel-replica-bag-2025-guide"
        elif cluster == "Louis Vuitton":
            overlaps = "lv-bag-authentication-guide; louis-vuitton-materials-guide"
        role_rows.append(
            {
                "URL": urls[index],
                "current role": f"Current role {index}",
                "final role": role,
                "primary intent": primary,
                "secondary intent": secondary,
                "cluster": cluster,
                "final disposition": disposition,
                "confidence": "high",
                "closest-overlap pages": overlaps,
                "planned phase": "phase 2",
                "approved-correction dependency": "sanitized dependency",
                "freshness disposition": "retain dated framing"
                if "2026" in slug
                else "make evergreen",
                "URL action": "none; URL unchanged",
            }
        )
    _write_csv(role_path, role_fields, role_rows)
    finding_fields = [
        "finding ID",
        "page",
        "rule",
        "original classification",
        "final owner disposition",
        "status",
        "linked edit operation",
        "phase",
        "validation",
        "controlling record",
    ]
    _write_csv(
        finding_path,
        finding_fields,
        [
            {
                "finding ID": "finding-1",
                "page": "chanel-replica-bag-2025-guide",
                "rule": "metadata",
                "original classification": "review",
                "final owner disposition": "defer",
                "status": "deferred",
                "linked edit operation": "P2-CHANEL-ROLE",
                "phase": "Phase 2",
                "validation": "role preserved",
                "controlling record": "fixture",
            }
        ],
    )
    readiness_fields = [
        "page URL",
        "current final role",
        "primary readiness status",
        "approved operations",
        "deferred operations",
        "visual blockers",
        "factual blockers",
        "paired-page or cluster dependency",
        "title can be drafted",
        "H1 can be drafted",
        "meta can be drafted",
        "section outline can be drafted",
        "body copy can be drafted",
        "recommended drafting batch",
    ]
    readiness_rows = [
        {
            "page URL": row["URL"],
            "current final role": row["final role"],
            "primary readiness status": "blocked_by_factual_evidence",
            "approved operations": "none",
            "deferred operations": "role-aligned review",
            "visual blockers": "none",
            "factual blockers": "UEQ-fixture: verify scoped claims",
            "paired-page or cluster dependency": "fixture cluster",
            "title can be drafted": "no",
            "H1 can be drafted": "no",
            "meta can be drafted": "no",
            "section outline can be drafted": "yes",
            "body copy can be drafted": "no",
            "recommended drafting batch": "fixture",
        }
        for row in role_rows
    ]
    _write_csv(readiness_path, readiness_fields, readiness_rows)
    roadmap.write_text(
        "# Sanitized planning-only roadmap\n\nNo drafting or URL operations.\n",
        encoding="utf-8",
    )
    _database(database, role_rows)
    return role_path, finding_path, roadmap, readiness_path, database


def _database(path: Path, roles: list[dict[str, str]]) -> None:
    connection = sqlite3.connect(path)
    connection.executescript("""
        CREATE TABLE page_identities (id TEXT PRIMARY KEY, canonical_url TEXT, current_article_version_id TEXT);
        CREATE TABLE article_versions (id TEXT PRIMARY KEY, normalized_content_hash TEXT, normalized_article_json TEXT);
    """)
    for index, row in enumerate(roles):
        article_id = f"article-{index:02d}"
        digest = hashlib.sha256(row["URL"].encode()).hexdigest()
        article = {
            "title": f"Fixture title {row['final role']}",
            "meta_description": f"Fixture metadata {index}",
            "normalized_at": "2026-07-15T01:00:00+00:00",
            "sections": [
                {"heading": {"level": 1, "text": f"Fixture H1 {row['final role']}"}},
                {"heading": {"level": 2, "text": "Existing evidence section"}},
            ],
        }
        connection.execute(
            "INSERT INTO page_identities VALUES (?, ?, ?)",
            (f"page-{index:02d}", row["URL"], article_id),
        )
        connection.execute(
            "INSERT INTO article_versions VALUES (?, ?, ?)",
            (article_id, digest, json.dumps(article)),
        )
    connection.commit()
    connection.close()


def _snapshot(tmp_path: Path) -> Path:
    source = tmp_path / "pilot-001"
    shutil.copytree(FIXTURE_ROOT / "kb" / "pilot-001", source)
    output = tmp_path / "snapshot"
    build_knowledge_snapshot([source], output)
    return output


def _context(tmp_path: Path) -> tuple[Path, Path]:
    role, findings, roadmap, readiness, database = _planning_fixture(tmp_path)
    output = tmp_path / "context"
    build_page_context(role, findings, roadmap, output, database, readiness)
    return output, database


def _mapped(tmp_path: Path) -> tuple[Path, Path, Path]:
    snapshot = _snapshot(tmp_path)
    context, database = _context(tmp_path)
    output = tmp_path / "mapped"
    map_content_opportunities(snapshot, context, output)
    return snapshot, context, database


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _edit_review(path: Path, changes: dict[str, dict[str, str]]) -> None:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    for row in rows:
        row.update(changes.get(row["opportunity_id"], {}))
    _write_csv(path, fields, rows)


def test_knowledge_snapshot_is_stable_and_filters_internal_stale_contradicted(
    tmp_path: Path,
) -> None:
    source = tmp_path / "pilot-001"
    shutil.copytree(FIXTURE_ROOT / "kb" / "pilot-001", source)
    output = tmp_path / "snapshot"
    first = build_knowledge_snapshot([source], output)
    first_bytes = {item.name: item.read_bytes() for item in output.iterdir()}
    second = build_knowledge_snapshot([source], output)
    assert first == second
    assert first_bytes == {item.name: item.read_bytes() for item in output.iterdir()}
    publishable = _jsonl(output / "approved-knowledge-snapshot.jsonl")
    assert all(item["publication_status"] != "internal_only" for item in publishable)
    assert first.internal_only_count == 1
    assert first.excluded_entry_ids == [
        "knowledge-chanel-stale",
        "knowledge-lv-contradicted",
    ]
    assert any(item["required_qualification"] for item in publishable)


def test_sanitized_three_topic_source_fixture_remains_offline_and_unapproved(
    tmp_path: Path,
) -> None:
    output = tmp_path / "community-import"
    summary = import_community_manifest(
        FIXTURE_ROOT / "pilot-community-manifest.json", output
    )
    assert summary["source_record_count"] == 6
    assert summary["candidate_claim_count"] == 6
    sources = _jsonl(output / "normalized-source-records.jsonl")
    assert all(
        not item.get("source_url")
        or item["source_url"].startswith("https://example.invalid/")
        for item in sources
    )
    unsupported = {
        "claim-chanel-unsupported",
        "claim-hermes-unsupported",
        "claim-lv-unsupported",
    }
    candidates = _jsonl(output / "candidate-claims.jsonl")
    assert unsupported <= {item["claim_id"] for item in candidates}
    snapshot = _snapshot(tmp_path / "knowledge")
    publishable = _jsonl(snapshot / "approved-knowledge-snapshot.jsonl")
    assert unsupported.isdisjoint({item["source_claim_id"] for item in publishable})


def test_conflicting_knowledge_ids_fail_safely(tmp_path: Path) -> None:
    first = tmp_path / "batch-a"
    second = tmp_path / "batch-b"
    shutil.copytree(FIXTURE_ROOT / "kb" / "pilot-001", first)
    second.mkdir()
    record = _jsonl(first / "approved-knowledge.jsonl")[0]
    record["approved_claim"] = "Conflicting wording."
    (second / "approved-knowledge.jsonl").write_text(
        json.dumps(record) + "\n", encoding="utf-8"
    )
    with pytest.raises(ContentOpsError, match="conflicting content"):
        build_knowledge_snapshot([first, second], tmp_path / "out")


def test_page_context_has_exact_roles_urls_and_is_read_only(tmp_path: Path) -> None:
    role, findings, roadmap, readiness, database = _planning_fixture(tmp_path)
    before = database.read_bytes()
    output = tmp_path / "context"
    manifest = build_page_context(role, findings, roadmap, output, database, readiness)
    records = _jsonl(output / "page-context.jsonl")
    assert manifest["page_count"] == 25 == len(records)
    assert len({item["page_url"] for item in records}) == 25
    chanel = next(
        item for item in records if "chanel-replica-bag-2025-guide" in item["page_url"]
    )
    assert chanel["final_role"] == "Classic Flap vs Chanel 22 vs Chanel 19 comparison"
    assert all("merge" not in item["final_role"].lower() for item in records)
    assert len({item["content_cluster"] for item in records}) == 7
    assert database.read_bytes() == before


def test_mapping_preserves_roles_qualifications_and_intent_separation(
    tmp_path: Path,
) -> None:
    snapshot, context, _ = _mapped(tmp_path)
    del snapshot, context
    opportunities = _jsonl(tmp_path / "mapped" / "content-opportunities.jsonl")
    chanel = [
        item
        for item in opportunities
        if item["knowledge_entry_ids"] == ["knowledge-chanel-19"]
    ]
    assert any(
        "chanel-replica-bag-2025-guide" in (item["target_page_url"] or "")
        for item in chanel
    )
    assert any(
        "best-chanel-replica-bags-guide" in (item["target_page_url"] or "")
        for item in chanel
    )
    assert all(item["required_qualification"] for item in chanel)
    auth = [
        item
        for item in opportunities
        if item["knowledge_entry_ids"] == ["knowledge-chanel-auth"]
    ]
    assert auth and all(
        "auth"
        in (
            item["page_role"] if "page_role" in item else item["mapping_reason"]
        ).lower()
        for item in auth
    )
    assert all(
        "best-chanel-replica-bags-guide" not in (item["target_page_url"] or "")
        for item in auth
    )
    buying = [
        item
        for item in opportunities
        if item["knowledge_entry_ids"] == ["knowledge-chanel-buying"]
    ]
    assert buying and all(
        "auth" not in (item["target_page_url"] or "").lower() for item in buying
    )
    internal = next(
        item
        for item in opportunities
        if item["knowledge_entry_ids"] == ["knowledge-chanel-internal"]
    )
    assert (
        internal["opportunity_type"] == "internal_only_research"
        and internal["target_page_url"] is None
    )


def test_mapping_new_article_no_action_ambiguity_and_existing_suppression(
    tmp_path: Path,
) -> None:
    _mapped(tmp_path)
    opportunities = _jsonl(tmp_path / "mapped" / "content-opportunities.jsonl")
    coussin = next(
        item
        for item in opportunities
        if item["knowledge_entry_ids"] == ["knowledge-lv-coussin"]
    )
    assert coussin["opportunity_type"] == "new_article_candidate"
    assert coussin["user_question"] and coussin["overlap_risk"]
    assert "Temporal durability" in coussin["mapping_reason"]
    forecast = next(
        item
        for item in opportunities
        if item["knowledge_entry_ids"] == ["knowledge-lv-forecast"]
    )
    assert forecast["opportunity_type"] == "no_action"
    assert any("temporal" in flag for flag in forecast["conflict_flags"])
    dated = next(
        item
        for item in opportunities
        if item["knowledge_entry_ids"] == ["knowledge-lv-2026-trend"]
    )
    assert "2026" in (dated["target_page_url"] or "")
    assert dated["temporal_scope"]["valid_until"].startswith("2026-")
    canvas = next(
        item
        for item in opportunities
        if item["knowledge_entry_ids"] == ["knowledge-lv-canvas"]
    )
    assert "ambiguous_exact_mapping" in canvas["conflict_flags"]
    assert canvas["confidence"] == "low"
    assert all(
        item["opportunity_type"] != "new_article_candidate"
        for item in opportunities
        if item["knowledge_entry_ids"] == ["knowledge-chanel-19"]
    )


def test_blank_decisions_pending_and_changed_target_must_exist(tmp_path: Path) -> None:
    _mapped(tmp_path)
    review = tmp_path / "review"
    export_opportunity_review(tmp_path / "mapped", review)
    rows = json.loads(
        (review / "opportunity-review-queue.json").read_text(encoding="utf-8")
    )
    assert rows and all(row["owner_decision"] == "" for row in rows)
    summary = apply_opportunity_decisions(
        review / "opportunity-review-queue.csv",
        tmp_path / "mapped",
        tmp_path / "pending",
    )
    assert summary["pending_count"] == len(rows)
    first_bytes = {
        item.name: item.read_bytes() for item in (tmp_path / "pending").iterdir()
    }
    assert summary == apply_opportunity_decisions(
        review / "opportunity-review-queue.csv",
        tmp_path / "mapped",
        tmp_path / "pending",
    )
    assert first_bytes == {
        item.name: item.read_bytes() for item in (tmp_path / "pending").iterdir()
    }
    opportunity_id = rows[0]["opportunity_id"]
    _edit_review(
        review / "opportunity-review-queue.csv",
        {
            opportunity_id: {
                "owner_decision": "approved_with_changes",
                "owner_rationale": "Owner reviewed.",
                "reviewer": "owner",
                "reviewed_at": "2026-07-15T04:00:00Z",
                "approved_target": "https://reinaluxe.co/not-in-context/",
                "approved_type": rows[0]["opportunity_type"],
                "approved_location": "reviewed location",
                "drafting_priority": "low",
            }
        },
    )
    with pytest.raises(ContentOpsError, match="not in page context"):
        apply_opportunity_decisions(
            review / "opportunity-review-queue.csv",
            tmp_path / "mapped",
            tmp_path / "invalid",
        )


def test_conflicting_decisions_and_internal_upgrade_fail_safely(
    tmp_path: Path,
) -> None:
    _mapped(tmp_path)
    review = tmp_path / "review"
    export_opportunity_review(tmp_path / "mapped", review)
    review_path = review / "opportunity-review-queue.csv"
    with review_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    first = rows[0]
    first.update(
        {
            "owner_decision": "approved",
            "owner_rationale": "First final decision.",
            "reviewer": "owner",
            "reviewed_at": "2026-07-15T04:00:00Z",
            "drafting_priority": "low",
        }
    )
    conflicting = dict(first)
    conflicting["owner_decision"] = "rejected"
    _write_csv(review_path, fields, [*rows, conflicting])
    with pytest.raises(ContentOpsError, match="conflicting final decisions"):
        apply_opportunity_decisions(review_path, tmp_path / "mapped", tmp_path / "bad")

    export_opportunity_review(tmp_path / "mapped", review)
    queue = json.loads(
        (review / "opportunity-review-queue.json").read_text(encoding="utf-8")
    )
    internal = next(
        row for row in queue if row["knowledge_entry_id"] == "knowledge-chanel-internal"
    )
    _edit_review(
        review_path,
        {
            internal["opportunity_id"]: {
                "owner_decision": "approved",
                "owner_rationale": "Invalid publication upgrade.",
                "reviewer": "owner",
                "reviewed_at": "2026-07-15T04:00:00Z",
                "drafting_priority": "low",
            }
        },
    )
    with pytest.raises(ContentOpsError, match="internal-only knowledge cannot"):
        apply_opportunity_decisions(
            review_path, tmp_path / "mapped", tmp_path / "internal-upgrade"
        )


def _approved_decisions(tmp_path: Path) -> tuple[Path, Path, Path, Path, str]:
    snapshot, context, database = _mapped(tmp_path)
    review = tmp_path / "review"
    export_opportunity_review(tmp_path / "mapped", review)
    rows = json.loads(
        (review / "opportunity-review-queue.json").read_text(encoding="utf-8")
    )
    existing = next(
        row
        for row in rows
        if row["proposed_target_page"] and row["knowledge_required_qualification"]
    )
    rejected = next(
        row for row in rows if row["opportunity_id"] != existing["opportunity_id"]
    )
    deferred = next(
        row
        for row in rows
        if row["opportunity_id"]
        not in {existing["opportunity_id"], rejected["opportunity_id"]}
    )
    common = {
        "reviewer": "owner",
        "reviewed_at": "2026-07-15T04:00:00Z",
        "drafting_priority": "not_scheduled",
    }
    _edit_review(
        review / "opportunity-review-queue.csv",
        {
            existing["opportunity_id"]: {
                **common,
                "owner_decision": "approved",
                "owner_rationale": "Approved scoped opportunity.",
                "drafting_priority": "medium",
            },
            rejected["opportunity_id"]: {
                **common,
                "owner_decision": "rejected",
                "owner_rationale": "Not suitable.",
            },
            deferred["opportunity_id"]: {
                **common,
                "owner_decision": "defer",
                "owner_rationale": "Review later.",
            },
        },
    )
    decisions = tmp_path / "decisions"
    apply_opportunity_decisions(
        review / "opportunity-review-queue.csv", tmp_path / "mapped", decisions
    )
    return snapshot, context, database, decisions, existing["opportunity_id"]


def test_approved_decisions_create_hash_locked_manifest_only(tmp_path: Path) -> None:
    snapshot, context, database, decisions, approved_id = _approved_decisions(tmp_path)
    output = tmp_path / "manifest"
    manifest = build_content_change_manifest(
        decisions, snapshot, context, output, database
    )
    assert manifest.approved_opportunity_ids == [approved_id]
    assert len(manifest.page_version_constraints) == 1
    assert manifest.knowledge_snapshot_hash and manifest.page_context_snapshot_hash
    assert manifest.required_qualifications
    assert "redirect" in manifest.prohibited_operations
    assert "article_copy_generated" not in manifest.owner_approval
    assert (
        json.loads((output / "manifest-summary.json").read_text(encoding="utf-8"))[
            "article_copy_generated"
        ]
        is False
    )


def test_stale_page_context_and_missing_knowledge_block_manifest(
    tmp_path: Path,
) -> None:
    snapshot, context, database, decisions, _ = _approved_decisions(tmp_path)
    connection = sqlite3.connect(database)
    target = next(iter(_jsonl(decisions / "approved-opportunities.jsonl")))[
        "target_page_url"
    ]
    current = connection.execute(
        "SELECT current_article_version_id FROM page_identities WHERE canonical_url=?",
        (target,),
    ).fetchone()[0]
    connection.execute(
        "UPDATE article_versions SET normalized_content_hash=? WHERE id=?",
        ("f" * 64, current),
    )
    connection.commit()
    connection.close()
    with pytest.raises(ContentOpsError, match="stale"):
        build_content_change_manifest(
            decisions, snapshot, context, tmp_path / "stale", database
        )

    snapshot2, context2, database2, decisions2, _ = _approved_decisions(
        tmp_path / "second"
    )
    lines = _jsonl(decisions2 / "decision-knowledge-index.jsonl")
    approved = _jsonl(decisions2 / "approved-opportunities.jsonl")[0]
    opportunity = next(
        item
        for item in _jsonl(decisions2 / "decision-opportunities.jsonl")
        if item["opportunity_id"] == approved["opportunity_id"]
    )
    missing_id = opportunity["knowledge_entry_ids"][0]
    (decisions2 / "decision-knowledge-index.jsonl").write_text(
        "".join(
            json.dumps(item, sort_keys=True) + "\n"
            for item in lines
            if item["knowledge_entry_id"] != missing_id
        ),
        encoding="utf-8",
    )
    with pytest.raises(
        ContentOpsError, match="does not match supplied snapshot|missing knowledge"
    ):
        build_content_change_manifest(
            decisions2, snapshot2, context2, tmp_path / "missing", database2
        )
