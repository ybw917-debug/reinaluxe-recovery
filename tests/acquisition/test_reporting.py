from datetime import UTC, datetime

from reinaluxe_recovery.acquisition import AcquisitionResult, AcquisitionSourceType
from reinaluxe_recovery.acquisition.reporting import render_acquisition


def test_report_contains_next_command(tmp_path):
    result = AcquisitionResult(
        acquisition_id="x",
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        source_type=AcquisitionSourceType.URL_LIST,
        output_directory=tmp_path,
        pages=(),
        manifest_path=tmp_path / "manifest.json",
    )
    assert "import-batch" in render_acquisition(result)
