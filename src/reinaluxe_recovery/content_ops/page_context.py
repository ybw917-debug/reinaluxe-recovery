"""Read-only page-context snapshot construction from authoritative local inputs."""

from __future__ import annotations

import csv
import json
import sqlite3
import unicodedata
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from reinaluxe_recovery.community.io import (
    prepare_output,
    read_json,
    write_csv,
    write_json,
    write_jsonl,
)
from reinaluxe_recovery.community.normalization import (
    content_hash,
    normalize_text,
    stable_id,
)
from reinaluxe_recovery.content_ops.common import (
    file_sha256,
    model_payload,
    split_values,
    typed_jsonl,
)
from reinaluxe_recovery.content_ops.errors import PageContextError
from reinaluxe_recovery.domain.content_ops import PageContextRecord

PROHIBITED_OPERATIONS = [
    "automatic_drafting",
    "automatic_publication",
    "canonical_change",
    "content_merge",
    "database_mutation",
    "redirect",
    "url_change",
    "wordpress_edit",
]

BRANDS = {
    "bottega veneta": "Bottega Veneta",
    "celine": "Celine",
    "chanel": "Chanel",
    "goyard": "Goyard",
    "gucci": "Gucci",
    "hermes": "Hermès",
    "louis vuitton": "Louis Vuitton",
    "the row": "The Row",
}
MODELS = (
    "Alma",
    "Anjou",
    "Birkin 25",
    "Chanel 19",
    "Chanel 22",
    "Classic Flap",
    "Constance 18",
    "Coussin PM",
    "Dauphine",
    "Kelly 28",
    "Margaux",
    "Mini Gold Ball",
    "Mini Kelly II",
    "Multi-Pochette",
    "Neverfull",
    "Park Tote",
    "Pearl Crush",
    "Saïgon",
    "Saint Louis",
    "Speedy",
)
MATERIALS = (
    "Box leather",
    "Canvas",
    "Caviar leather",
    "Coated canvas",
    "Epi leather",
    "Epsom leather",
    "Lambskin",
    "Monogram canvas",
    "Togo leather",
    "Vachetta",
)


def build_page_context(
    role_matrix: Path,
    finding_register: Path,
    roadmap: Path,
    output: Path,
    database: Path,
    readiness: Path | None = None,
) -> dict[str, Any]:
    """Create exactly 25 contexts without changing SQLite or source artifacts."""
    roles = _read_csv(role_matrix)
    if len(roles) != 25:
        raise PageContextError("final page-role matrix must contain exactly 25 rows")
    urls = [row["URL"].strip() for row in roles]
    if len(urls) != len(set(urls)):
        raise PageContextError("final page-role matrix contains duplicate URLs")
    if any("merge" in row["final role"].casefold() for row in roles):
        raise PageContextError("final page-role matrix contains a merge candidate")
    if any(
        row["URL action"].strip().casefold() != "none; url unchanged" for row in roles
    ):
        raise PageContextError("every matrix URL action must remain unchanged")
    clusters = {row["cluster"].strip() for row in roles}
    if len(clusters) != 7:
        raise PageContextError("final page-role matrix must represent seven clusters")
    chanel_old = next(
        (row for row in roles if "chanel-replica-bag-2025-guide" in row["URL"]),
        None,
    )
    if chanel_old is None or chanel_old["final disposition"] != "Reposition":
        raise PageContextError("older Chanel page must remain Reposition")

    readiness_path = readiness or (
        role_matrix.parent.parent
        / "evidence-closure-package"
        / "page-drafting-readiness.csv"
    )
    readiness_rows = _read_csv(readiness_path)
    readiness_by_url = {row["page URL"].strip(): row for row in readiness_rows}
    findings_by_slug: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in _read_csv(finding_register):
        findings_by_slug[row["page"].strip()].append(row)
    articles = _read_current_articles(database)
    if set(articles) != set(urls):
        missing = sorted(set(urls) - set(articles))
        extra = sorted(set(articles) - set(urls))
        raise PageContextError(
            f"database/matrix URL mismatch; missing={len(missing)}, extra={len(extra)}"
        )
    context_created_at = max(item["normalized_at"] for item in articles.values())
    slug_urls = {_slug(url): url for url in urls}
    hubs_by_cluster = {
        row["cluster"]: row["URL"] for row in roles if row["final disposition"] == "Hub"
    }
    cluster_members: dict[str, list[str]] = defaultdict(list)
    for row in roles:
        cluster_members[row["cluster"]].append(row["URL"])

    records: list[PageContextRecord] = []
    for row in sorted(roles, key=lambda item: item["URL"]):
        url = row["URL"].strip()
        article = articles[url]
        ready = readiness_by_url.get(url, {})
        slug = _slug(url)
        findings = findings_by_slug.get(slug, [])
        approved = split_values(ready.get("approved operations"))
        approved.extend(
            item["linked edit operation"]
            for item in findings
            if item["status"].casefold() == "approved"
            and item["linked edit operation"].strip()
        )
        deferred = split_values(ready.get("deferred operations"))
        deferred.extend(
            item["linked edit operation"]
            for item in findings
            if item["status"].casefold() != "approved"
            and item["linked edit operation"].strip()
        )
        composite = " ".join(
            [
                url,
                article["title"],
                row["current role"],
                row["final role"],
                row["primary intent"],
                row["secondary intent"],
                row["cluster"],
            ]
        )
        brand, models, materials = _entities(composite)
        hub_url = _hub_for(row, hubs_by_cluster)
        supporting = (
            sorted(set(cluster_members[row["cluster"]]) - {url})
            if row["final disposition"] == "Hub"
            else []
        )
        overlaps = _resolve_overlaps(row["closest-overlap pages"], slug_urls)
        payload = {
            "schema_version": "1.0",
            "page_url": url,
            "page_identity_id": article["page_identity_id"],
            "article_version_id": article["article_version_id"],
            "page_content_hash": article["page_content_hash"],
            "current_title": article["title"],
            "current_h1": article["h1"],
            "current_meta_description": article["meta_description"],
            "current_role": row["current role"],
            "final_role": row["final role"],
            "primary_intent": row["primary intent"],
            "secondary_intents": split_values(row["secondary intent"]),
            "brand": brand,
            "models": models,
            "materials": materials,
            "content_cluster": row["cluster"],
            "hub_url": hub_url,
            "supporting_urls": supporting,
            "closest_overlap_urls": overlaps,
            "approved_operations": sorted(set(approved)),
            "deferred_operations": sorted(set(deferred)),
            "prohibited_operations": PROHIBITED_OPERATIONS,
            "section_outline": article["outline"],
            "factual_blockers": split_values(ready.get("factual blockers")),
            "visual_blockers": split_values(ready.get("visual blockers")),
            "freshness_status": row["freshness disposition"],
            "context_created_at": context_created_at,
        }
        hash_payload = _json_safe(payload)
        record = PageContextRecord.model_validate(
            {
                **payload,
                "page_context_id": stable_id(
                    "pctx",
                    {
                        "page_url": url,
                        "article_version_id": article["article_version_id"],
                        "final_role": row["final role"],
                    },
                ),
                "context_hash": content_hash(hash_payload),
            }
        )
        records.append(record)

    source_hashes = {
        "final_page_role_matrix": file_sha256(role_matrix),
        "final_finding_disposition_register": file_sha256(finding_register),
        "final_consolidated_edit_roadmap": file_sha256(roadmap),
        "page_drafting_readiness": file_sha256(readiness_path),
        "database_current_versions": content_hash(
            {
                url: {
                    "article_version_id": item["article_version_id"],
                    "content_hash": item["page_content_hash"],
                }
                for url, item in sorted(articles.items())
            }
        ),
    }
    manifest_base = {
        "schema_version": "1.0",
        "created_at": context_created_at.isoformat(),
        "page_count": len(records),
        "page_context_ids": [item.page_context_id for item in records],
        "context_hashes": {str(item.page_url): item.context_hash for item in records},
        "source_hashes": source_hashes,
        "authoritative_role_matrix": True,
        "database_access_mode": "read_only_immutable",
    }
    snapshot_id = stable_id("pcsnap", manifest_base)
    manifest = {
        **manifest_base,
        "page_context_snapshot_id": snapshot_id,
        "manifest_hash": content_hash(manifest_base),
    }
    prepare_output(output)
    write_jsonl(output / "page-context.jsonl", records)
    csv_fields = list(model_payload(records[0]))
    write_csv(
        output / "page-context.csv",
        csv_fields,
        [model_payload(item) for item in records],
    )
    write_json(output / "page-context-manifest.json", manifest)
    write_json(
        output / "page-context-summary.json",
        {
            "schema_version": "1.0",
            "page_context_snapshot_id": snapshot_id,
            "page_count": len(records),
            "cluster_count": len(clusters),
            "hub_count": len(hubs_by_cluster),
            "url_changes": 0,
            "database_writes": 0,
            "drafted_copy": False,
        },
    )
    return manifest


def validate_page_context(
    directory: Path,
) -> tuple[dict[str, Any], list[PageContextRecord]]:
    manifest = read_json(directory / "page-context-manifest.json")
    if not isinstance(manifest, dict):
        raise PageContextError("page context manifest must be an object")
    records = typed_jsonl(directory / "page-context.jsonl", PageContextRecord)
    base = {
        key: value
        for key, value in manifest.items()
        if key not in {"page_context_snapshot_id", "manifest_hash"}
    }
    if content_hash(base) != manifest.get("manifest_hash"):
        raise PageContextError("page context manifest hash mismatch")
    if len(records) != 25 or manifest.get("page_count") != 25:
        raise PageContextError("page context snapshot must contain exactly 25 pages")
    for record in records:
        record_payload = record.model_dump(
            mode="json", exclude={"page_context_id", "context_hash"}
        )
        record_payload["context_created_at"] = record.context_created_at.isoformat()
        if content_hash(record_payload) != record.context_hash:
            raise PageContextError(
                f"page context record hash mismatch: {record.page_context_id}"
            )
    expected = {str(item.page_url): item.context_hash for item in records}
    if expected != manifest.get("context_hashes"):
        raise PageContextError("page context records do not match manifest hashes")
    return manifest, records


def current_version_constraints(database: Path) -> dict[str, dict[str, str]]:
    articles = _read_current_articles(database)
    return {
        url: {
            "article_version_id": item["article_version_id"],
            "page_content_hash": item["page_content_hash"],
        }
        for url, item in sorted(articles.items())
    }


def _read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    except OSError as error:
        raise PageContextError(f"could not read planning input: {path.name}") from error


def _read_current_articles(database: Path) -> dict[str, dict[str, Any]]:
    resolved = database.resolve()
    uri = f"file:{resolved.as_posix()}?mode=ro&immutable=1"
    try:
        connection = sqlite3.connect(uri, uri=True)
        rows = connection.execute(
            """SELECT p.id, p.canonical_url, p.current_article_version_id,
                      a.normalized_content_hash, a.normalized_article_json
               FROM page_identities p
               JOIN article_versions a ON a.id = p.current_article_version_id
               ORDER BY p.canonical_url"""
        ).fetchall()
        connection.close()
    except sqlite3.Error as error:
        raise PageContextError("could not read current page versions") from error
    output: dict[str, dict[str, Any]] = {}
    for page_id, url, article_id, digest, raw_article in rows:
        article = json.loads(raw_article)
        headings = [
            section["heading"]["text"]
            for section in article.get("sections", [])
            if section.get("heading") and section["heading"].get("text")
        ]
        h1 = next(
            (
                section["heading"]["text"]
                for section in article.get("sections", [])
                if section.get("heading") and section["heading"].get("level") == 1
            ),
            article["title"],
        )
        normalized_at = datetime.fromisoformat(
            article["normalized_at"].replace("Z", "+00:00")
        )
        output[url] = {
            "page_identity_id": page_id,
            "article_version_id": article_id,
            "page_content_hash": digest,
            "title": article["title"],
            "h1": h1,
            "meta_description": article.get("meta_description"),
            "outline": headings,
            "normalized_at": normalized_at,
        }
    return output


def _entities(value: str) -> tuple[str | None, list[str], list[str]]:
    normalized = _fold(value)
    brand = next((label for term, label in BRANDS.items() if term in normalized), None)
    models = sorted(item for item in MODELS if _fold(item) in normalized)
    materials = sorted(item for item in MATERIALS if _fold(item) in normalized)
    return brand, models, materials


def _fold(value: str) -> str:
    return normalize_text(
        "".join(
            character
            for character in unicodedata.normalize("NFKD", value).casefold()
            if not unicodedata.combining(character)
        )
    )


def _slug(url: str) -> str:
    return url.rstrip("/").rsplit("/", 1)[-1]


def _resolve_overlaps(value: str, slug_urls: dict[str, str]) -> list[str]:
    resolved: set[str] = set()
    for part in value.split(";"):
        candidate = part.strip().strip("`")
        if candidate in slug_urls:
            resolved.add(slug_urls[candidate])
    return sorted(resolved)


def _hub_for(row: dict[str, str], hubs: dict[str, str]) -> str | None:
    if row["final disposition"] == "Hub":
        return None
    hub = hubs.get(row["cluster"])
    if (
        row["cluster"] == "Louis Vuitton"
        and "authentication"
        not in (row["final role"] + row["secondary intent"]).casefold()
    ):
        return None
    return hub


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value
