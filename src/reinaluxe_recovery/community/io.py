"""Safe deterministic local I/O helpers for community workflow artifacts."""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable, Mapping, Sequence
from io import StringIO
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from reinaluxe_recovery.community.contracts import LocalRecordReference
from reinaluxe_recovery.community.exceptions import (
    CommunityManifestError,
    CommunityPathError,
)
from reinaluxe_recovery.community.normalization import canonical_json


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CommunityManifestError(
            f"could not read valid JSON file: {path.name}"
        ) from error


def resolve_confined(root: Path, value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        raise CommunityPathError("local input paths must be relative to the manifest")
    try:
        resolved_root = root.resolve()
        resolved = (resolved_root / candidate).resolve()
    except OSError as error:
        raise CommunityPathError("local input path could not be resolved") from error
    if not resolved.is_relative_to(resolved_root):
        raise CommunityPathError("local input path escapes the manifest directory")
    return resolved


def read_local_record(
    root: Path, item: Mapping[str, Any], default_encoding: str
) -> list[dict[str, Any]]:
    """Expand one optional confined text/JSON record reference."""
    if "input_file" not in item:
        return [dict(item)]
    allowed_control = {"input_file", "input_format", "encoding"}
    inline = {key: value for key, value in item.items() if key not in allowed_control}
    try:
        reference = LocalRecordReference.model_validate(
            {
                "input_file": item.get("input_file"),
                "input_format": item.get("input_format"),
                "encoding": item.get("encoding", default_encoding),
            }
        )
    except ValidationError as error:
        raise CommunityManifestError(
            "referenced records require a relative path, text/json format, "
            "and explicit encoding"
        ) from error
    path = resolve_confined(root, str(reference.input_file))
    try:
        text = path.read_text(encoding=reference.encoding)
    except (OSError, LookupError, UnicodeError) as error:
        raise CommunityManifestError(
            f"could not decode local input file: {path.name}"
        ) from error
    if reference.input_format == "text":
        if "raw_excerpt" in inline:
            raise CommunityManifestError("text input cannot also define raw_excerpt")
        return [{**inline, "raw_excerpt": text}]
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise CommunityManifestError(
            f"local JSON input is invalid: {path.name}"
        ) from error
    records = payload if isinstance(payload, list) else [payload]
    if not all(isinstance(record, dict) for record in records):
        raise CommunityManifestError(
            "local JSON input must contain an object or object list"
        )
    return [{**record, **inline} for record in records]


def validate_record(
    model: type[BaseModel], value: Mapping[str, Any], label: str
) -> BaseModel:
    try:
        return model.model_validate(value)
    except ValidationError as error:
        details = "; ".join(
            f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
            for item in error.errors(include_url=False, include_input=False)
        )
        raise CommunityManifestError(f"invalid {label}: {details}") from error


def model_json(record: BaseModel) -> dict[str, Any]:
    return record.model_dump(mode="json")


def write_jsonl(path: Path, records: Iterable[BaseModel | Mapping[str, Any]]) -> None:
    lines = []
    for record in records:
        value = model_json(record) if isinstance(record, BaseModel) else dict(record)
        lines.append(canonical_json(value))
    write_text(path, "".join(f"{line}\n" for line in lines))


def write_json(path: Path, value: Any) -> None:
    write_text(
        path, f"{json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)}\n"
    )


def write_csv(
    path: Path, fieldnames: Sequence[str], rows: Iterable[Mapping[str, Any]]
) -> None:
    buffer = StringIO(newline="")
    writer = csv.DictWriter(
        buffer, fieldnames=fieldnames, lineterminator="\n", extrasaction="ignore"
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({key: _csv_value(row.get(key, "")) for key in fieldnames})
    write_text(path, buffer.getvalue())


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise CommunityManifestError("review CSV requires a header")
            return list(reader.fieldnames), list(reader)
    except OSError as error:
        raise CommunityManifestError(
            f"could not read review CSV: {path.name}"
        ) from error


def load_jsonl(path: Path, model: type[BaseModel]) -> list[BaseModel]:
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError as error:
        raise CommunityManifestError(
            f"could not read workflow input: {path.name}"
        ) from error
    records: list[BaseModel] = []
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            records.append(model.model_validate_json(line))
        except ValidationError as error:
            raise CommunityManifestError(
                f"invalid {path.name} record at line {number}"
            ) from error
    return records


def prepare_output(path: Path) -> None:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise CommunityManifestError("could not create output directory") from error


def write_text(path: Path, text: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.tmp")
        temporary.write_text(text, encoding="utf-8", newline="")
        temporary.replace(path)
    except OSError as error:
        raise CommunityManifestError(
            f"could not write output file: {path.name}"
        ) from error


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, dict)):
        return canonical_json(value)
    return str(value)
