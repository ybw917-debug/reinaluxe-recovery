"""Contract tests for strict versioned batch manifests."""

from copy import deepcopy
from typing import Any

import pytest
from pydantic import ValidationError

from reinaluxe_recovery.batch import BatchImportOptions, BatchManifest


def _manifest() -> dict[str, Any]:
    return {
        "contract_version": "1.0",
        "batch_id": "batch-contracts",
        "created_at": "2026-07-14T10:00:00+08:00",
        "default_fetched_at": "2026-07-14T09:30:00+08:00",
        "entries": [
            {
                "entry_id": "one",
                "html_path": "html/one.html",
                "source_url": "https://owner.example/one/",
            },
            {
                "entry_id": "two",
                "html_path": "html/two.html",
                "source_url": "https://owner.example/two/",
                "fetched_at": "2026-07-14T09:45:00+08:00",
            },
        ],
    }


def test_valid_manifest_inherits_timestamp_and_headers() -> None:
    """Defaults are explicit, immutable provenance inherited per entry."""
    data = _manifest()
    data["default_headers"] = {"content-type": "text/html", "x-source": "batch"}
    data["entries"][0]["headers"] = {"x-source": "entry"}

    manifest = BatchManifest.model_validate(data)

    assert manifest.contract_version == "1.0"
    assert manifest.effective_fetched_at(manifest.entries[0]).hour == 9
    assert manifest.effective_headers(manifest.entries[0]) == {
        "content-type": "text/html",
        "x-source": "entry",
    }


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda data: data.update(contract_version="2.0"), "contract_version"),
        (lambda data: data.update(created_at="2026-07-14T10:00:00"), "timezone"),
        (
            lambda data: data.update(default_fetched_at="2026-07-14T09:30:00"),
            "timezone",
        ),
        (lambda data: data.update(unexpected=True), "extra"),
        (
            lambda data: data["entries"][0].update(source_url="file:///tmp/a"),
            "URL",
        ),
        (
            lambda data: data["entries"][0].update(unexpected=True),
            "extra",
        ),
    ],
)
def test_manifest_rejects_invalid_version_dates_urls_and_unknown_fields(
    mutation: Any,
    message: str,
) -> None:
    data = _manifest()
    mutation(data)
    with pytest.raises(ValidationError, match=message):
        BatchManifest.model_validate(data)


def test_manifest_requires_effective_fetched_at() -> None:
    data = _manifest()
    data["default_fetched_at"] = None
    data["entries"][1].pop("fetched_at")

    with pytest.raises(ValidationError, match="requires fetched_at"):
        BatchManifest.model_validate(data)


@pytest.mark.parametrize("field", ["entry_id", "html_path"])
def test_manifest_rejects_duplicate_entry_identity_and_path(field: str) -> None:
    data = _manifest()
    data["entries"][1][field] = data["entries"][0][field]

    with pytest.raises(ValidationError, match=f"duplicate {field}"):
        BatchManifest.model_validate(data)


def test_batch_options_reject_duplicate_filters() -> None:
    with pytest.raises(ValidationError, match="duplicate entry_ids"):
        BatchImportOptions(entry_ids=["one", "one"])


def test_contract_round_trip_is_stable() -> None:
    manifest = BatchManifest.model_validate(deepcopy(_manifest()))
    assert BatchManifest.model_validate_json(manifest.model_dump_json()) == manifest
