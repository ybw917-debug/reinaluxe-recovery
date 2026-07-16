"""Separate runtime topic-knowledge database for research reuse."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from reinaluxe_recovery.community.normalization import content_hash, stable_id
from reinaluxe_recovery.research.analysis import ResearchAnalysisBundle
from reinaluxe_recovery.research.contracts import (
    OwnerResearchDecision,
    ResearchSnapshot,
)
from reinaluxe_recovery.research.errors import ResearchArtifactError

DEFAULT_RESEARCH_DATABASE = Path("data/research/runtime/research.sqlite")

_SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS research_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS topics (
    topic_id TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    refresh_after TEXT,
    deleted_at TEXT
);
CREATE TABLE IF NOT EXISTS topic_aliases (
    topic_id TEXT NOT NULL REFERENCES topics(topic_id),
    alias TEXT NOT NULL,
    alias_kind TEXT NOT NULL,
    PRIMARY KEY (topic_id, alias, alias_kind)
);
CREATE TABLE IF NOT EXISTS query_templates (
    topic_id TEXT NOT NULL REFERENCES topics(topic_id),
    template TEXT NOT NULL,
    PRIMARY KEY (topic_id, template)
);
CREATE TABLE IF NOT EXISTS sources (
    source_id TEXT PRIMARY KEY,
    normalized_url TEXT NOT NULL UNIQUE,
    payload_json TEXT NOT NULL,
    source_available INTEGER NOT NULL DEFAULT 1,
    deleted_at TEXT
);
CREATE TABLE IF NOT EXISTS topic_sources (
    topic_id TEXT NOT NULL REFERENCES topics(topic_id),
    source_id TEXT NOT NULL REFERENCES sources(source_id),
    PRIMARY KEY (topic_id, source_id)
);
CREATE TABLE IF NOT EXISTS claims (
    claim_id TEXT PRIMARY KEY,
    normalized_claim_text TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS topic_claims (
    topic_id TEXT NOT NULL REFERENCES topics(topic_id),
    claim_id TEXT NOT NULL REFERENCES claims(claim_id),
    PRIMARY KEY (topic_id, claim_id)
);
CREATE TABLE IF NOT EXISTS evidence (
    evidence_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES sources(source_id),
    payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS claim_evidence (
    claim_id TEXT NOT NULL REFERENCES claims(claim_id),
    evidence_id TEXT NOT NULL REFERENCES evidence(evidence_id),
    relationship TEXT NOT NULL,
    PRIMARY KEY (claim_id, evidence_id, relationship)
);
CREATE TABLE IF NOT EXISTS article_evidence (
    article_url TEXT NOT NULL,
    evidence_id TEXT NOT NULL REFERENCES evidence(evidence_id),
    research_id TEXT NOT NULL,
    PRIMARY KEY (article_url, evidence_id, research_id)
);
CREATE TABLE IF NOT EXISTS images (
    image_id TEXT PRIMARY KEY,
    normalized_image_url TEXT NOT NULL UNIQUE,
    source_id TEXT NOT NULL REFERENCES sources(source_id),
    payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS image_claims (
    image_id TEXT NOT NULL REFERENCES images(image_id),
    claim_id TEXT NOT NULL REFERENCES claims(claim_id),
    PRIMARY KEY (image_id, claim_id)
);
CREATE TABLE IF NOT EXISTS owner_decisions (
    decision_id TEXT PRIMARY KEY,
    subject_type TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS research_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    research_id TEXT NOT NULL,
    snapshot_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
"""


class ResearchTopicDatabase:
    """SQLite persistence isolated from the production application database."""

    def __init__(
        self,
        path: Path = DEFAULT_RESEARCH_DATABASE,
        *,
        production_database_path: Path | None = None,
    ) -> None:
        self.path = path
        if (
            production_database_path
            and path.resolve() == production_database_path.resolve()
        ):
            raise ResearchArtifactError(
                "research database must not be the production database"
            )

    def initialize(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.path) as connection:
                connection.executescript(_SCHEMA)
                connection.execute(
                    "INSERT OR REPLACE INTO research_metadata(key, value) VALUES ('schema_version', '1.0')"
                )
        except (OSError, sqlite3.Error) as error:
            raise ResearchArtifactError(
                "could not initialize research runtime database"
            ) from error

    def store_bundle(
        self, bundle: ResearchAnalysisBundle, snapshot: ResearchSnapshot
    ) -> None:
        self.initialize()
        evidence_by_id = {
            item.evidence_id: item for item in bundle.source_evidence_records
        }
        try:
            with sqlite3.connect(self.path) as connection:
                connection.execute("PRAGMA foreign_keys = ON")
                for topic in bundle.topics:
                    payload = _json(topic)
                    connection.execute(
                        """INSERT INTO topics VALUES (?, ?, ?, ?)
                           ON CONFLICT(topic_id) DO UPDATE SET
                           payload_json=excluded.payload_json,
                           refresh_after=excluded.refresh_after,
                           deleted_at=excluded.deleted_at""",
                        (
                            topic.topic_id,
                            payload,
                            topic.refresh_after.isoformat()
                            if topic.refresh_after
                            else None,
                            topic.deleted_at.isoformat() if topic.deleted_at else None,
                        ),
                    )
                    connection.execute(
                        "DELETE FROM topic_aliases WHERE topic_id=?", (topic.topic_id,)
                    )
                    for alias in topic.aliases:
                        connection.execute(
                            "INSERT INTO topic_aliases VALUES (?, ?, 'alias')",
                            (topic.topic_id, alias),
                        )
                    for synonym in topic.synonyms:
                        connection.execute(
                            "INSERT INTO topic_aliases VALUES (?, ?, 'synonym')",
                            (topic.topic_id, synonym),
                        )
                    for template in topic.query_templates:
                        connection.execute(
                            "INSERT OR IGNORE INTO query_templates VALUES (?, ?)",
                            (topic.topic_id, template),
                        )
                for source in bundle.run.source_candidates:
                    connection.execute(
                        """INSERT INTO sources VALUES (?, ?, ?, ?, NULL)
                           ON CONFLICT(source_id) DO UPDATE SET
                           payload_json=excluded.payload_json,
                           source_available=excluded.source_available""",
                        (
                            source.source_id,
                            str(source.normalized_url),
                            _json(source),
                            int(source.source_available),
                        ),
                    )
                for claim in bundle.candidate_claims:
                    connection.execute(
                        """INSERT INTO claims VALUES (?, ?, ?)
                           ON CONFLICT(claim_id) DO UPDATE SET
                           normalized_claim_text=excluded.normalized_claim_text,
                           payload_json=excluded.payload_json""",
                        (claim.claim_id, claim.normalized_claim_text, _json(claim)),
                    )
                    for topic_id in claim.topic_ids:
                        connection.execute(
                            "INSERT OR IGNORE INTO topic_claims VALUES (?, ?)",
                            (topic_id, claim.claim_id),
                        )
                for evidence in bundle.source_evidence_records:
                    connection.execute(
                        """INSERT INTO evidence VALUES (?, ?, ?)
                           ON CONFLICT(evidence_id) DO UPDATE SET
                           source_id=excluded.source_id,
                           payload_json=excluded.payload_json""",
                        (evidence.evidence_id, evidence.source_id, _json(evidence)),
                    )
                    for topic_id in evidence.proposed_topic_ids:
                        connection.execute(
                            "INSERT OR IGNORE INTO topic_sources VALUES (?, ?)",
                            (topic_id, evidence.source_id),
                        )
                    if bundle.plan.target_article_url:
                        connection.execute(
                            "INSERT OR IGNORE INTO article_evidence VALUES (?, ?, ?)",
                            (
                                str(bundle.plan.target_article_url),
                                evidence.evidence_id,
                                bundle.research_id,
                            ),
                        )
                for link in bundle.claim_evidence_links:
                    if link.evidence_id not in evidence_by_id:
                        raise ResearchArtifactError(
                            f"claim link references missing evidence: {link.evidence_id}"
                        )
                    connection.execute(
                        "INSERT OR REPLACE INTO claim_evidence VALUES (?, ?, ?)",
                        (link.claim_id, link.evidence_id, link.relationship.value),
                    )
                for image in bundle.run.image_candidates:
                    connection.execute(
                        """INSERT INTO images VALUES (?, ?, ?, ?)
                           ON CONFLICT(image_id) DO UPDATE SET
                           normalized_image_url=excluded.normalized_image_url,
                           source_id=excluded.source_id,
                           payload_json=excluded.payload_json""",
                        (
                            image.image_id,
                            str(image.normalized_image_url),
                            image.source_id,
                            _json(image),
                        ),
                    )
                    for claim_id in image.linked_claim_ids:
                        connection.execute(
                            "INSERT OR IGNORE INTO image_claims VALUES (?, ?)",
                            (image.image_id, claim_id),
                        )
                for decision in snapshot.owner_decisions:
                    connection.execute(
                        "INSERT OR REPLACE INTO owner_decisions VALUES (?, ?, ?, ?)",
                        (
                            decision.decision_id,
                            decision.subject_type,
                            decision.subject_id,
                            _json(decision),
                        ),
                    )
                assert snapshot.snapshot_hash is not None
                connection.execute(
                    "INSERT OR REPLACE INTO research_snapshots VALUES (?, ?, ?, ?)",
                    (
                        snapshot.snapshot_id,
                        snapshot.research_id,
                        snapshot.snapshot_hash,
                        _json(snapshot),
                    ),
                )
        except sqlite3.Error as error:
            raise ResearchArtifactError(
                "could not persist research snapshot"
            ) from error

    def topic_summary(self, topic_id: str) -> dict[str, Any] | None:
        self.initialize()
        with sqlite3.connect(self.path) as connection:
            topic = connection.execute(
                "SELECT payload_json FROM topics WHERE topic_id=?", (topic_id,)
            ).fetchone()
            if topic is None:
                return None
            aliases = [
                row[0]
                for row in connection.execute(
                    "SELECT alias FROM topic_aliases WHERE topic_id=? ORDER BY alias",
                    (topic_id,),
                )
            ]
            claims = [
                row[0]
                for row in connection.execute(
                    "SELECT claim_id FROM topic_claims WHERE topic_id=? ORDER BY claim_id",
                    (topic_id,),
                )
            ]
            sources = [
                row[0]
                for row in connection.execute(
                    "SELECT source_id FROM topic_sources WHERE topic_id=? ORDER BY source_id",
                    (topic_id,),
                )
            ]
        return {
            "topic": json.loads(topic[0]),
            "aliases": aliases,
            "claim_ids": claims,
            "source_ids": sources,
        }


def build_research_snapshot(
    bundle: ResearchAnalysisBundle,
    database_path: Path = DEFAULT_RESEARCH_DATABASE,
    *,
    production_database_path: Path | None = None,
) -> ResearchSnapshot:
    """Create a deterministic snapshot and persist it only in research SQLite."""
    plan_hash = bundle.plan.plan_hash
    run_hash = bundle.run.run_hash
    if plan_hash is None or run_hash is None:
        raise ResearchArtifactError("analysis plan and run must be hash locked")
    decisions = [
        OwnerResearchDecision(
            decision_id=stable_id(
                "research_decision",
                {"subject_type": "opportunity", "subject_id": item.opportunity_id},
            ),
            subject_type="opportunity",
            subject_id=item.opportunity_id,
        )
        for item in bundle.article_content_opportunities
    ]
    decisions.extend(
        OwnerResearchDecision(
            decision_id=stable_id(
                "research_decision",
                {"subject_type": "image", "subject_id": item.image_id},
            ),
            subject_type="image",
            subject_id=item.image_id,
        )
        for item in bundle.run.image_candidates
    )
    base: dict[str, Any] = {
        "snapshot_id": stable_id(
            "research_snapshot",
            {"research_id": bundle.research_id, "run_hash": run_hash},
        ),
        "research_id": bundle.research_id,
        "request_hash": bundle.plan.request_hash,
        "plan_hash": plan_hash,
        "run_hash": run_hash,
        "topic_ids": sorted(item.topic_id for item in bundle.topics),
        "source_ids": sorted(item.source_id for item in bundle.run.source_candidates),
        "claim_ids": sorted(item.claim_id for item in bundle.candidate_claims),
        "image_ids": sorted(item.image_id for item in bundle.run.image_candidates),
        "contradiction_ids": sorted(
            item.contradiction_id for item in bundle.contradictions
        ),
        "opportunity_ids": sorted(
            item.opportunity_id for item in bundle.article_content_opportunities
        ),
        "owner_decisions": sorted(decisions, key=lambda item: item.decision_id),
        "source_availability": {
            item.source_id: item.source_available
            for item in sorted(
                bundle.run.source_candidates, key=lambda value: value.source_id
            )
        },
    }
    snapshot = ResearchSnapshot(**base, snapshot_hash=content_hash(_json_payload(base)))
    ResearchTopicDatabase(
        database_path, production_database_path=production_database_path
    ).store_bundle(bundle, snapshot)
    return snapshot


def _json(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_payload(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {key: _json_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_payload(item) for item in value]
    return value
