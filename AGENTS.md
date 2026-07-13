# Repository Guidance for Coding Agents

## Mission

ReinaLuxe Recovery OS is an AI-native SEO recovery and knowledge management
system. Preserve the product goals, sprint scope, and owner-authored work while
making focused, reviewable changes.

## Current stage

Sprint 1 Issue 001 is repository scaffolding only. A dependency or planned
boundary is not an implemented feature. Crawler, parser, database-model, SEO,
LLM, Reddit, WordPress, Pinterest, and dashboard work requires a separate,
explicitly approved issue.

## Working rules

- Confirm the Git root and inspect `git status` before editing.
- Treat existing modified and untracked files as owner work; integrate rather
  than discard, restore, or overwrite it blindly.
- Use Python 3.12 and keep importable code under `src/reinaluxe_recovery/`.
- Use `uv` for environment and dependency management; do not mix package
  managers or manually edit a generated lockfile.
- Keep secrets out of the repository. Document only non-secret placeholders in
  `.env.example`.
- Keep local or generated data out of Git.
- Do not commit or push unless the task explicitly authorizes it.

## Design guidance

- Keep the Typer/Rich CLI thin; product behavior belongs behind a separate
  application boundary when future issues define it.
- Use Pydantic at validated input and settings boundaries.
- Reserve SQLAlchemy for a future persistence layer; no database models or
  migrations exist in this scaffold.
- Prefer small, typed modules and standard-library solutions where practical.

## Quality gates

Only after dependency setup and validation are authorized, run:

```console
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

Add or update tests for behavior changes, and update documentation and the
changelog when scope or developer workflow changes.
