"""Offline, owner-editable asset manifest generation for future research pages."""

from __future__ import annotations

import csv
import hashlib
import importlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from reinaluxe_recovery.community.io import write_csv
from reinaluxe_recovery.community.normalization import stable_id
from reinaluxe_recovery.research.contracts import (
    AssetManifestRecord,
    ImageSourceCategory,
)
from reinaluxe_recovery.research.errors import ResearchArtifactError

ASSET_MANIFEST_FIELDS = (
    "asset_id",
    "relative_path",
    "file_type",
    "sha256",
    "perceptual_hash",
    "brand",
    "model",
    "size",
    "leather",
    "hardware",
    "angle_or_detail",
    "source_category",
    "source_code",
    "owner_reviewed",
    "owner_photographed",
    "publication_permission",
    "target_topics",
    "notes",
)

_FILE_TYPES = {
    ".avif": "image/avif",
    ".bmp": "image/bmp",
    ".gif": "image/gif",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".webp": "image/webp",
    ".csv": "text/csv",
    ".json": "application/json",
    ".md": "text/markdown",
    ".txt": "text/plain",
}
_FOLDER_CATEGORIES = {
    "owner-original": ImageSourceCategory.OWNER_ORIGINAL,
    "owner-submitted": ImageSourceCategory.OWNER_SUBMITTED,
    "qc-images": ImageSourceCategory.QC_IMAGE,
    "seller-shot": ImageSourceCategory.SELLER_SHOT,
    "supplier-provided": ImageSourceCategory.SUPPLIER_PROVIDED,
    "official-reference": ImageSourceCategory.OFFICIAL_REFERENCE,
    "community-images": ImageSourceCategory.COMMUNITY_IMAGE,
}
_DETAIL_FOLDERS = {"hardware", "leather", "stitching", "structure", "measurements"}


def build_asset_manifest(
    asset_root: Path,
    output: Path,
    *,
    brand: str,
    model: str,
    size: str,
) -> list[AssetManifestRecord]:
    """Inventory supported local files without changing any source asset."""
    root = asset_root.resolve()
    if not root.is_dir():
        raise ResearchArtifactError(f"asset root is not a directory: {asset_root}")
    output_resolved = output.resolve()
    existing = _existing_records(output)
    records: list[AssetManifestRecord] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix().casefold()):
        if not path.is_file() or path.suffix.casefold() not in _FILE_TYPES:
            continue
        resolved = path.resolve()
        if resolved == output_resolved or resolved.name == f".{output.name}.tmp":
            continue
        relative = resolved.relative_to(root)
        relative_key = relative.as_posix()
        prior = existing.get(relative_key)
        inferred_category, inferred_note = _infer_source_category(relative)
        detail = next(
            (
                part.casefold()
                for part in relative.parts
                if part.casefold() in _DETAIL_FOLDERS
            ),
            "",
        )
        source_category = inferred_category
        owner_reviewed = False
        owner_photographed = False
        if prior is not None:
            source_category = prior.source_category
            owner_reviewed = prior.owner_reviewed
            owner_photographed = prior.owner_photographed
        notes = _base_notes(prior.notes if prior else "", inferred_note)
        records.append(
            AssetManifestRecord(
                asset_id=(
                    prior.asset_id
                    if prior is not None
                    else stable_id("asset", relative_key)
                ),
                relative_path=relative,
                file_type=_FILE_TYPES[path.suffix.casefold()],
                sha256=_sha256(resolved),
                perceptual_hash=_perceptual_hash(resolved),
                brand=prior.brand if prior and prior.brand else brand,
                model=prior.model if prior and prior.model else model,
                size=prior.size if prior and prior.size else size,
                leather=prior.leather if prior else "",
                hardware=prior.hardware if prior else "",
                angle_or_detail=(prior.angle_or_detail if prior else detail),
                source_category=source_category,
                source_code=prior.source_code if prior else "",
                owner_reviewed=owner_reviewed,
                owner_photographed=owner_photographed,
                publication_permission=(prior.publication_permission if prior else ""),
                target_topics=prior.target_topics if prior else [],
                notes=notes,
            )
        )
    records = _mark_duplicates(records)
    write_csv(
        output,
        ASSET_MANIFEST_FIELDS,
        [
            {
                **item.model_dump(mode="json"),
                "relative_path": item.relative_path.as_posix(),
            }
            for item in records
        ],
    )
    return records


def _existing_records(path: Path) -> dict[str, AssetManifestRecord]:
    if not path.is_file():
        return {}
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except OSError as error:
        raise ResearchArtifactError(
            f"could not read existing asset manifest: {path}"
        ) from error
    output: dict[str, AssetManifestRecord] = {}
    for row in rows:
        payload: dict[str, Any] = dict(row)
        for field in ("owner_reviewed", "owner_photographed"):
            payload[field] = str(payload.get(field, "")).casefold() == "true"
        raw_topics = str(payload.get("target_topics", "")).strip()
        try:
            payload["target_topics"] = json.loads(raw_topics) if raw_topics else []
        except json.JSONDecodeError:
            payload["target_topics"] = [
                item.strip() for item in raw_topics.split(",") if item.strip()
            ]
        if not payload.get("source_category"):
            payload["source_category"] = None
        try:
            record = AssetManifestRecord.model_validate(payload)
        except ValueError as error:
            raise ResearchArtifactError(
                f"invalid existing asset manifest record: {payload.get('relative_path', '')}"
            ) from error
        output[record.relative_path.as_posix()] = record
    return output


def _infer_source_category(
    relative: Path,
) -> tuple[ImageSourceCategory | None, str]:
    for part in relative.parts:
        category = _FOLDER_CATEGORIES.get(part.casefold())
        if category is None:
            continue
        if category is ImageSourceCategory.OWNER_ORIGINAL:
            return (
                None,
                "provisional_source_category=owner_original; explicit owner record required",
            )
        return (
            category,
            f"provisional_source_category={category.value}; owner review required",
        )
    return None, "source category requires owner review"


def _mark_duplicates(
    records: list[AssetManifestRecord],
) -> list[AssetManifestRecord]:
    exact: dict[str, list[AssetManifestRecord]] = defaultdict(list)
    visual: dict[str, list[AssetManifestRecord]] = defaultdict(list)
    for record in records:
        exact[record.sha256].append(record)
        if record.perceptual_hash:
            visual[record.perceptual_hash].append(record)
    updates: dict[str, list[str]] = defaultdict(list)
    for group in exact.values():
        ordered = sorted(group, key=lambda item: item.relative_path.as_posix())
        for duplicate in ordered[1:]:
            updates[duplicate.asset_id].append(
                f"exact_duplicate_of={ordered[0].asset_id}"
            )
    for group in visual.values():
        ordered = sorted(group, key=lambda item: item.relative_path.as_posix())
        for duplicate in ordered[1:]:
            if duplicate.sha256 != ordered[0].sha256:
                updates[duplicate.asset_id].append(
                    f"probable_visual_duplicate_of={ordered[0].asset_id}"
                )
    return [
        record.model_copy(
            update={
                "notes": "; ".join(
                    value
                    for value in [record.notes, *updates.get(record.asset_id, [])]
                    if value
                )
            }
        )
        for record in records
    ]


def _base_notes(existing: str, inferred: str) -> str:
    retained = [
        item.strip()
        for item in existing.split(";")
        if item.strip()
        and not item.strip().startswith(
            (
                "exact_duplicate_of=",
                "probable_visual_duplicate_of=",
                "provisional_source_category=",
            )
        )
        and item.strip() != "source category requires owner review"
    ]
    return "; ".join([*retained, inferred])


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _perceptual_hash(path: Path) -> str:
    if not _FILE_TYPES[path.suffix.casefold()].startswith("image/"):
        return ""
    try:
        image_module: Any = importlib.import_module("PIL.Image")
    except ImportError:
        return ""
    try:
        with image_module.open(path) as image:
            pixels = list(image.convert("L").resize((8, 8)).getdata())
    except (OSError, ValueError):
        return ""
    average = sum(pixels) / len(pixels)
    bits = "".join("1" if value >= average else "0" for value in pixels)
    return f"{int(bits, 2):016x}"
