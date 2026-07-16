"""Offline-only diagnostics for previously captured research artifacts."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from reinaluxe_recovery.community.io import prepare_output, write_csv, write_json
from reinaluxe_recovery.community.normalization import stable_id
from reinaluxe_recovery.research.query_integrity import topic_relevance_hits
from reinaluxe_recovery.research.screening import (
    organization_cluster_key,
    regional_variant,
    registrable_domain,
)


def audit_original_smoke(input_directory: Path, output: Path) -> dict[str, Any]:
    """Re-screen captured CSVs without network, GLM, or claim generation."""
    prepare_output(output)
    source_rows = _read_csv(input_directory / "retained-source-register.csv")
    image_rows = _read_csv(input_directory / "image-source-candidates.csv")
    source_diagnostics = [_source_diagnostic(row) for row in source_rows]
    visual_diagnostics = [_visual_diagnostic(row) for row in image_rows]
    organizations = {row["organization_cluster_id"] for row in source_diagnostics}
    passed = [row for row in source_diagnostics if row["topic_relevance_passed"]]
    resolved = [row for row in visual_diagnostics if row["resolved"]]
    summary = {
        "schema_version": "1.0",
        "offline_only": True,
        "provider_calls_made": 0,
        "glm_calls_made": 0,
        "claims_generated": 0,
        "original_retained_sources": len(source_rows),
        "topic_relevance_passed": len(passed),
        "topic_relevance_failed": len(source_rows) - len(passed),
        "organization_cluster_count": len(organizations),
        "organization_cluster_reduction": max(0, len(source_rows) - len(organizations)),
        "original_image_candidates": len(image_rows),
        "valid_resolved_image_candidates": len(resolved),
        "unresolved_visual_page_candidates": len(image_rows) - len(resolved),
    }
    write_csv(
        output / "original-smoke-source-diagnostic.csv",
        list(source_diagnostics[0]) if source_diagnostics else ["source_id"],
        source_diagnostics,
    )
    write_csv(
        output / "original-smoke-visual-diagnostic.csv",
        list(visual_diagnostics[0]) if visual_diagnostics else ["image_id"],
        visual_diagnostics,
    )
    write_json(output / "validation.json", summary)
    return summary


def _source_diagnostic(row: dict[str, str]) -> dict[str, Any]:
    url = row.get("normalized_url") or row.get("source_url") or ""
    host = (urlsplit(url).hostname or row.get("domain") or "unknown.invalid").casefold()
    registered = registrable_domain(host)
    organization = stable_id(
        "organization", organization_cluster_key(host, ["Louis Vuitton"])
    )
    family = row.get("query_family") or ""
    value = " ".join((row.get("title", ""), row.get("snippet", ""), url))
    hits = topic_relevance_hits(family, value)
    return {
        "source_id": row.get("source_id", ""),
        "query_family": family,
        "url": url,
        "topic_relevance_passed": bool(hits),
        "topic_anchor_hits": hits,
        "exclusion_reason": "" if hits else "topic_relevance_failed",
        "exact_host": host,
        "registrable_domain": registered,
        "organization_cluster_id": organization,
        "regional_variant": regional_variant(host, registered),
        "independent_source_cluster_id": organization,
    }


def _visual_diagnostic(row: dict[str, str]) -> dict[str, Any]:
    locator_type, locator = _resolved_locator(row)
    resolved = bool(locator)
    return {
        "image_id": row.get("image_id", ""),
        "source_id": row.get("source_id", ""),
        "source_page_url": row.get("source_page_url", ""),
        "resolved": resolved,
        "candidate_resolution_status": (
            "resolved_image_candidate" if resolved else "visual_page_candidate"
        ),
        "image_locator_type": locator_type if resolved else "none",
        "image_locator": locator,
        "page_may_contain_images": True,
        "actual_image_reference_available": resolved,
        "qualification_failure_reason": (
            "" if resolved else "no image URL, asset ID, page image ID, or local path"
        ),
    }


def _resolved_locator(row: dict[str, str]) -> tuple[str, str]:
    for key, locator_type in (
        ("image_url", "provider_image_url"),
        ("existing_page_image_id", "existing_page_image_id"),
        ("local_file_path", "local_file_path"),
        ("image_locator", row.get("image_locator_type") or "source_specific_metadata"),
    ):
        value = row.get(key, "").strip()
        if value:
            locator_type_value: str = str(locator_type)
            return locator_type_value, value
    raw_metadata = row.get("provider_media_metadata", "").strip()
    try:
        metadata = json.loads(raw_metadata) if raw_metadata else {}
    except json.JSONDecodeError:
        metadata = {}
    if isinstance(metadata, dict):
        for key in ("asset_url", "src", "image_id", "asset_id"):
            metadata_value = metadata.get(key)
            if metadata_value is not None and str(metadata_value).strip():
                return "source_specific_metadata", str(metadata_value).strip()
    return "", ""


def _read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))
    except OSError as error:
        raise ValueError(
            f"could not read captured smoke artifact: {path.name}"
        ) from error
