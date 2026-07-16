# Research topic database

Research runtime state is isolated at `data/research/runtime/research.sqlite`, which is ignored by Git. This database is never the production application database. The implementation refuses an explicitly supplied research path that resolves to the production path.

The schema stores versioned topic payloads, aliases and synonyms, query templates, reusable normalized sources, source availability and deletion state, atomic claims, topic-to-claim and topic-to-source links, evidence, claim/evidence relationships, article/evidence links, image candidates, image/claim links, owner decisions, and immutable research snapshots. A source or claim can be reused by several topics, and evidence can be linked to several article URLs over subsequent research runs.

Article analysis opens the production SQLite file with `mode=ro&immutable=1`. Snapshot persistence opens only the research database. Runtime refresh dates and deletion/availability fields are retained rather than deleting provenance history.
