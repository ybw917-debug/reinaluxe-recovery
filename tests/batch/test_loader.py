"""Secure local loader tests for manifests and HTML files."""

import json
from pathlib import Path

import pytest

from reinaluxe_recovery.batch import (
    BatchEntryFileError,
    BatchManifest,
    BatchManifestError,
    BatchPathError,
    BatchSourceHashMismatchError,
    load_batch_manifest,
    load_html_entry,
    resolve_entry_path,
    validate_manifest_paths,
)
from reinaluxe_recovery.importing import hash_html_body

FIXTURES = Path(__file__).parent / "fixtures"


def _write_manifest(tmp_path: Path, entry: dict[str, object]) -> Path:
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps(
            {
                "contract_version": "1.0",
                "batch_id": "loader-test",
                "created_at": "2026-07-14T10:00:00+00:00",
                "default_fetched_at": "2026-07-14T09:00:00+00:00",
                "entries": [entry],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_load_valid_manifest_and_disabled_entry() -> None:
    manifest = load_batch_manifest(FIXTURES / "valid-manifest.json")
    assert [item.entry_id for item in manifest.entries] == [
        "article-a",
        "disabled-example",
    ]
    assert manifest.entries[1].enabled is False


def test_invalid_json_has_clear_manifest_error(tmp_path: Path) -> None:
    path = tmp_path / "invalid.json"
    path.write_text("{", encoding="utf-8")
    with pytest.raises(BatchManifestError, match="invalid batch manifest"):
        load_batch_manifest(path)


@pytest.mark.parametrize("unsafe", ["../outside.html", "C:/absolute.html"])
def test_absolute_and_traversal_paths_are_rejected(
    tmp_path: Path,
    unsafe: str,
) -> None:
    path = _write_manifest(
        tmp_path,
        {
            "entry_id": "unsafe",
            "html_path": unsafe,
            "source_url": "https://owner.example/unsafe/",
        },
    )
    manifest = load_batch_manifest(path)
    with pytest.raises(BatchPathError):
        resolve_entry_path(path, manifest.entries[0])


def test_missing_file_is_an_entry_error(tmp_path: Path) -> None:
    path = _write_manifest(
        tmp_path,
        {
            "entry_id": "missing",
            "html_path": "html/missing.html",
            "source_url": "https://owner.example/missing/",
        },
    )
    entry = load_batch_manifest(path).entries[0]
    with pytest.raises(BatchEntryFileError, match="could not read HTML"):
        load_html_entry(path, entry)


def test_equivalent_resolved_paths_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps(
            {
                "contract_version": "1.0",
                "batch_id": "equivalent-paths",
                "created_at": "2026-07-14T10:00:00+00:00",
                "default_fetched_at": "2026-07-14T09:00:00+00:00",
                "entries": [
                    {
                        "entry_id": "one",
                        "html_path": "html/one.html",
                        "source_url": "https://owner.example/one/",
                    },
                    {
                        "entry_id": "two",
                        "html_path": "html/../html/one.html",
                        "source_url": "https://owner.example/two/",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = load_batch_manifest(path)
    with pytest.raises(BatchPathError, match="same html_path"):
        validate_manifest_paths(path, manifest)


def test_source_hash_match_and_mismatch_before_parsing(tmp_path: Path) -> None:
    html = "<html lang='en'><title>Hash</title><main><p>Body</p></main></html>"
    html_path = tmp_path / "html" / "hash.html"
    html_path.parent.mkdir()
    html_path.write_text(html, encoding="utf-8")
    digest = hash_html_body(html)
    path = _write_manifest(
        tmp_path,
        {
            "entry_id": "hash",
            "html_path": "html/hash.html",
            "source_url": "https://owner.example/hash/",
            "expected_source_hash": digest,
        },
    )
    entry = load_batch_manifest(path).entries[0]
    assert load_html_entry(path, entry).source_hash == digest

    invalid = entry.model_copy(update={"expected_source_hash": "0" * 64})
    with pytest.raises(BatchSourceHashMismatchError, match="source hash mismatch"):
        load_html_entry(path, invalid)


def test_loader_does_not_mutate_manifest_contract() -> None:
    manifest = BatchManifest.model_validate_json(
        (FIXTURES / "valid-manifest.json").read_bytes()
    )
    before = manifest.model_dump_json()
    load_html_entry(FIXTURES / "valid-manifest.json", manifest.entries[0])
    assert manifest.model_dump_json() == before
