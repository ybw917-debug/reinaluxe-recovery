from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from reinaluxe_recovery.cli import app

runner = CliRunner()


def test_community_command_help_and_existing_help_remain_available() -> None:
    for command in (
        "community-import",
        "community-export-review",
        "community-apply-decisions",
        "community-build-kb",
        "community-build-snapshot",
        "content-build-page-context",
        "community-map-opportunities",
        "community-export-opportunity-review",
        "community-apply-opportunity-decisions",
        "content-build-change-manifest",
        "import-html",
        "import-batch",
        "audit-articles",
        "acquire-site",
    ):
        result = runner.invoke(app, [command, "--help"])
        assert result.exit_code == 0, result.stdout


def test_community_import_cli_writes_required_artifacts(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "import_batch_id": "cli-pilot",
                "created_at": "2026-07-15T10:00:00+08:00",
                "sources": [
                    {
                        "platform": "owner",
                        "community_or_channel": "offline fixture",
                        "source_type": "owner_note",
                        "retrieved_at": "2026-07-15T10:00:00+08:00",
                        "language": "en",
                        "raw_excerpt": "Minimal retained excerpt.",
                        "source_scope": "test only",
                        "copyright_retention_mode": "necessary_excerpt_only",
                        "visibility": "internal_only",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "output"
    result = runner.invoke(
        app,
        ["community-import", "--manifest", str(manifest), "--output", str(output)],
    )
    assert result.exit_code == 0, result.stdout
    assert {item.name for item in output.iterdir()} == {
        "candidate-claims.jsonl",
        "evidence-records.jsonl",
        "import-summary.json",
        "import-warnings.json",
        "normalized-source-records.jsonl",
    }
