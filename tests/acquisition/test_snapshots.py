from datetime import UTC, datetime
from uuid import uuid4

import pytest

from reinaluxe_recovery.acquisition import (
    AcquiredPage,
    AcquisitionRequest,
    AcquisitionSourceType,
    AcquisitionStatus,
)
from reinaluxe_recovery.acquisition.exceptions import SnapshotError
from reinaluxe_recovery.acquisition.snapshots import (
    build_manifest,
    confined_path,
    persist_page,
)


def test_snapshot_hash_unchanged_and_manifest(tmp_path) -> None:
    page = AcquiredPage(
        entry_id="stable",
        requested_url="https://example.com/a",
        final_url="https://example.com/a",
        fetched_at=datetime.now(UTC),
        status_code=200,
        status=AcquisitionStatus.FETCHED,
        duration_ms=1,
    )
    first = persist_page(tmp_path, page, b"<html>ok</html>", overwrite=False)
    second = persist_page(tmp_path, page, b"<html>ok</html>", overwrite=False)
    assert (
        second.status is AcquisitionStatus.UNCHANGED
        and first.source_hash == second.source_hash
    )
    request = AcquisitionRequest(
        acquisition_id=str(uuid4()),
        created_at=datetime.now(UTC),
        source_type=AcquisitionSourceType.URL_LIST,
        explicit_urls=("https://example.com/a",),
        allowed_hosts=frozenset({"example.com"}),
        output_directory=tmp_path,
        user_agent="x",
    )
    assert (
        build_manifest(request, [first]).entries[0].expected_source_hash
        == first.source_hash
    )
    with pytest.raises(SnapshotError):
        confined_path(tmp_path, __import__("pathlib").Path("../escape"))
