"""Offline provider-result reclassification and comparison artifacts."""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path
from typing import Any

from reinaluxe_recovery.community.io import prepare_output, write_csv, write_text
from reinaluxe_recovery.community.normalization import content_hash, normalize_text
from reinaluxe_recovery.research.artifacts import load_research_request
from reinaluxe_recovery.research.errors import ResearchArtifactError
from reinaluxe_recovery.research.planning import build_research_plan
from reinaluxe_recovery.research.query_integrity import build_preview_queries
from reinaluxe_recovery.research.screening import screen_source_candidate


def export_provider_comparison(
    request_path: Path,
    query_families: list[str],
    brave_run: Path,
    zhipu_run: Path,
    output: Path,
) -> list[dict[str, Any]]:
    """Reclassify both raw registers with current rules and compare providers."""
    prepare_output(output)
    plan = build_research_plan(load_research_request(request_path))
    queries = build_preview_queries(plan, query_families, maximum_results=10)
    query_by_id = {query.query_id: query for query in queries}
    policies = {item.source_lane: item for item in plan.source_lane_policies}
    summaries = [
        _summarize_run("brave-web-search", brave_run, query_by_id, policies),
        _summarize_run("zhipu-web-search-v2-offline", zhipu_run, query_by_id, policies),
    ]
    fields = [
        "provider",
        "evaluation_mode",
        "calls",
        "returned_raw_results",
        "original_retained_sources",
        "reclassified_retained_sources",
        "reclassified_exclusions",
        "topic_relevance_failed",
        "source_lane_mismatch",
        "psp_gaming_false_positive",
        "corrupted_content",
        "commercial_sources",
        "expert_sources",
        "coverage_sufficient_for_synthesis",
    ]
    write_csv(output / "provider-comparison-register.csv", fields, summaries)
    brave = summaries[0]
    zhipu = summaries[1]
    decision = (
        "Brave coverage was sufficient for cross-source synthesis."
        if brave["coverage_sufficient_for_synthesis"]
        else "Brave coverage was insufficient; cross-source synthesis must remain stopped."
    )
    write_text(
        output / "provider-comparison-report.md",
        (
            "# Brave versus Zhipu provider comparison\n\n"
            "Both provider registers were evaluated offline with the same current "
            "conjunctive relevance, source-lane, gaming false-positive, commercial, "
            "and corrupted-content rules. The Zhipu v2 provider was not called again.\n\n"
            "| Provider | Calls | Raw | Original retained | Reclassified retained | "
            "Lane mismatch | Relevance failed |\n"
            "|---|---:|---:|---:|---:|---:|---:|\n"
            f"| Brave Web Search | {brave['calls']} | "
            f"{brave['returned_raw_results']} | {brave['original_retained_sources']} | "
            f"{brave['reclassified_retained_sources']} | "
            f"{brave['source_lane_mismatch']} | {brave['topic_relevance_failed']} |\n"
            f"| Zhipu Web Search v2 (offline) | {zhipu['calls']} | "
            f"{zhipu['returned_raw_results']} | {zhipu['original_retained_sources']} | "
            f"{zhipu['reclassified_retained_sources']} | "
            f"{zhipu['source_lane_mismatch']} | {zhipu['topic_relevance_failed']} |\n\n"
            f"{decision}\n\n"
            "No result page was fetched, no Reddit request was made outside either "
            "provider, and no image search or download was performed for this comparison.\n"
        ),
    )
    return summaries


def _summarize_run(
    provider: str,
    run: Path,
    query_by_id: dict[str, Any],
    policies: dict[Any, Any],
) -> dict[str, Any]:
    result_path = run / "query-results-register.csv"
    call_path = run / "provider-call-register.csv"
    if not result_path.is_file() or not call_path.is_file():
        raise ResearchArtifactError(
            f"provider comparison input is incomplete: {run.name}"
        )
    results = _read_csv(result_path)
    calls = _read_csv(call_path)
    reasons: Counter[str] = Counter()
    lanes: Counter[str] = Counter()
    retained = 0
    seen_urls: set[str] = set()
    seen_content: set[str] = set()
    for row in results:
        query = query_by_id.get(row.get("query_id", ""))
        if query is None:
            reasons["unknown_query"] += 1
            continue
        candidate, reason = screen_source_candidate(
            query,
            {
                "provider": provider,
                "provider_result_id": row.get("provider_result_id"),
                "url": row.get("url"),
                "title": row.get("title"),
                "snippet": row.get("snippet_or_content"),
                "published_at": row.get("published_at") or None,
                "retrieved_at": row.get("retrieved_at") or None,
                "provider_access_classification": row.get(
                    "provider_access_classification"
                )
                or "provider_returned_snippet",
            },
            policies,
        )
        if candidate is None:
            reasons[reason or "invalid_source"] += 1
            continue
        normalized_url = str(candidate.normalized_url)
        content_key = normalize_text(
            " | ".join(value for value in (candidate.title, candidate.snippet) if value)
        ).casefold()
        content_key = content_hash(content_key) if content_key else ""
        if normalized_url in seen_urls:
            reasons["exact_duplicate_url"] += 1
            continue
        if content_key and content_key in seen_content:
            reasons["identical_title_snippet_duplicate"] += 1
            continue
        seen_urls.add(normalized_url)
        if content_key:
            seen_content.add(content_key)
        retained += 1
        lanes[candidate.source_lane.value] += 1
    completed_calls = [row for row in calls if row.get("status") == "completed"]
    return {
        "provider": provider,
        "evaluation_mode": "live_register_reclassification"
        if provider == "brave-web-search"
        else "offline_reclassification",
        "calls": len(completed_calls),
        "returned_raw_results": sum(
            _integer(row.get("returned_raw_results")) for row in calls
        ),
        "original_retained_sources": sum(
            row.get("status") == "retained" for row in results
        ),
        "reclassified_retained_sources": retained,
        "reclassified_exclusions": len(results) - retained,
        "topic_relevance_failed": reasons["topic_relevance_failed"],
        "source_lane_mismatch": reasons["source_lane_mismatch"],
        "psp_gaming_false_positive": reasons["psp_gaming_false_positive"],
        "corrupted_content": reasons["corrupted_content"],
        "commercial_sources": lanes["commercial_observation"],
        "expert_sources": lanes["expert_editorial"],
        "coverage_sufficient_for_synthesis": retained >= 3,
    }


def _read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))
    except (OSError, UnicodeError, csv.Error) as error:
        raise ResearchArtifactError(
            f"could not read provider register: {path.name}"
        ) from error


def _integer(value: object) -> int:
    try:
        return int(str(value or "0"))
    except ValueError:
        return 0
