"""Shared deterministic helpers for Stage 009B artifacts."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from reinaluxe_recovery.community.exceptions import CommunityWorkflowError
from reinaluxe_recovery.community.io import load_jsonl, read_json
from reinaluxe_recovery.community.normalization import content_hash
from reinaluxe_recovery.content_ops.errors import ContentOpsError


def typed_jsonl[ModelT: BaseModel](path: Path, model: type[ModelT]) -> list[ModelT]:
    try:
        return [model.model_validate(item) for item in load_jsonl(path, model)]
    except (CommunityWorkflowError, ValueError) as error:
        raise ContentOpsError(f"invalid workflow artifact: {path.name}") from error


def typed_json[ModelT: BaseModel](path: Path, model: type[ModelT]) -> ModelT:
    try:
        value = read_json(path)
        return model.model_validate(value)
    except (CommunityWorkflowError, ValueError) as error:
        raise ContentOpsError(f"invalid workflow artifact: {path.name}") from error


def file_sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise ContentOpsError(
            f"could not read workflow artifact: {path.name}"
        ) from error


def hash_model_payload(model: BaseModel, excluded: set[str]) -> str:
    return content_hash(
        {
            key: value
            for key, value in model.model_dump(mode="json").items()
            if key not in excluded
        }
    )


def model_payload(value: BaseModel) -> dict[str, Any]:
    return value.model_dump(mode="json")


def split_values(value: str | None) -> list[str]:
    if value is None:
        return []
    normalized = value.strip()
    if not normalized or normalized.casefold() == "none":
        return []
    return sorted(
        {
            part.strip()
            for part in normalized.replace("|", ";").split(";")
            if part.strip() and part.strip().casefold() != "none"
        }
    )
