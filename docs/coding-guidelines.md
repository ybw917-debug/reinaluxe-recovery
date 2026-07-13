# Coding Guidelines

## Python baseline

- Target Python 3.12.
- Add type hints to functions and public attributes.
- Prefer small, cohesive modules and descriptive names.
- Use `pathlib` for filesystem paths.
- Add concise docstrings to public APIs and explain decisions rather than
  restating code in comments.

## Structure and boundaries

- Keep source code under `src/reinaluxe_recovery/` and tests under `tests/`.
- Keep Typer/Rich CLI code focused on translating input and presenting output.
- Use Pydantic for validated boundaries and pydantic-settings for future
  environment-backed settings.
- Reserve SQLAlchemy for a future persistence layer; do not introduce database
  models or migrations without an approved design.
- Avoid adding speculative abstractions or integrations before their issues
  define requirements.

## Quality

- Keep imports explicit and free of side effects.
- Write deterministic unit tests that do not require network access.
- Cover public behavior and edge cases rather than implementation details.
- Run pytest, Ruff, and mypy through `uv` after the environment is prepared and
  the task authorizes validation.

## Configuration, data, and logging

- Read configuration from the environment; never hard-code secrets.
- Keep `.env.example` non-secret and update it when settings are introduced.
- Do not commit local databases, collected content, logs, or generated data.
- Avoid logging credentials, tokens, personal data, or sensitive collected
  content.

## Documentation

- Update the relevant document when architectural boundaries, scope, or
  developer commands change.
- Record notable changes in `CHANGELOG.md` without inventing dates or release
  commitments.
