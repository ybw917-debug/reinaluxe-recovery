# Development Workflow

## 1. Start with repository state

Work from the repository root. Before editing, confirm the root and inspect the
working tree so existing owner changes are not lost:

```console
git rev-parse --show-toplevel
git status
```

## 2. Validate the environment

Python 3.12 and `uv` are required. Resolve Python through `uv`; do not rely on
the system-level `python` command:

```console
uv --version
uv python find 3.12
```

After dependency setup is explicitly approved, create or update the environment:

```console
uv sync --python 3.12 --group dev
uv run python --version
```

Keep the generated `uv.lock` eligible for version control; do not edit it by
hand.

For an isolated local database workflow, use an explicit ignored or temporary
path:

```powershell
uv run reinaluxe-recovery db-init --database data\reinaluxe-recovery.db
uv run reinaluxe-recovery list-pages --database data\reinaluxe-recovery.db
```

Database-backed commands call Alembic programmatically and safely bring the
selected SQLite file to the current revision. Never add database or JSON output
files to Git.

## 3. Make a focused change

- Keep each change within its approved issue.
- Preserve unrelated modified and untracked files.
- Put importable Python code in `src/reinaluxe_recovery/`.
- Add or update tests for behavior changes.
- Update documentation and `CHANGELOG.md` when scope or workflow changes.

## 4. Run quality checks

Once the environment is prepared and validation is authorized, run:

```console
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

CLI changes also require an isolated smoke workflow: initialize a temporary
database, import an existing offline fixture, list pages, show the page, and
remove the temporary directory afterward.

## 5. Review the result

Inspect the final diff and status. Confirm that no secrets, local data, or
unrelated owner work are included. Commit and push only when explicitly
authorized.
