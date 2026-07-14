"""Owner-facing acquisition report."""

from reinaluxe_recovery.acquisition.contracts import AcquisitionResult


def render_acquisition(result: AcquisitionResult) -> str:
    lines = [
        f"Acquisition: {result.acquisition_id}",
        f"Discovered: {result.discovered_count}",
        f"Fetched: {result.fetched_count}; unchanged: {result.unchanged_count}; skipped: {result.skipped_count}; failed: {result.failed_count}",
    ]
    for page in result.pages:
        lines.append(
            f"- {page.status.value}: {page.requested_url}{f' ({page.error_message})' if page.error_message else ''}"
        )
    if result.manifest_path:
        lines.extend(
            [
                f"Manifest: {result.manifest_path}",
                f'Next: uv run reinaluxe-recovery import-batch "{result.manifest_path}" --dry-run',
            ]
        )
    return "\n".join(lines)
