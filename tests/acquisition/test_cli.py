from datetime import UTC, datetime

from typer.testing import CliRunner

from reinaluxe_recovery.acquisition import AcquisitionResult, AcquisitionSourceType
from reinaluxe_recovery.cli import app

runner = CliRunner()


def test_acquire_help() -> None:
    result = runner.invoke(app, ["acquire-site", "--help"])
    assert result.exit_code == 0 and "--allowed-host" in result.stdout


def test_invalid_source_configuration() -> None:
    result = runner.invoke(app, ["acquire-site", "--allowed-host", "example.com"])
    assert result.exit_code == 2


def test_cli_result_and_next_step(tmp_path, monkeypatch) -> None:
    url_list = tmp_path / "urls.txt"
    url_list.write_text("https://example.com/a\n", encoding="utf-8")

    class StubWorkflow:
        def run(self, request):
            return AcquisitionResult(
                acquisition_id=request.acquisition_id,
                started_at=datetime.now(UTC),
                completed_at=datetime.now(UTC),
                source_type=AcquisitionSourceType.URL_LIST,
                output_directory=request.output_directory,
                pages=(),
                manifest_path=request.output_directory / "manifest.json",
            )

    monkeypatch.setattr("reinaluxe_recovery.cli.AcquisitionWorkflow", StubWorkflow)
    result = runner.invoke(
        app,
        [
            "acquire-site",
            "--url-list",
            str(url_list),
            "--allowed-host",
            "example.com",
            "--output-directory",
            str(tmp_path / "out"),
        ],
    )
    assert result.exit_code == 0 and "import-batch" in result.stdout
