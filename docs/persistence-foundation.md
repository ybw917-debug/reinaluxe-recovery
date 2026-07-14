# Persistence Foundation

## Stage 004A scope

Stage 004A supplies local infrastructure only:

- typed SQLAlchemy 2.x ORM metadata;
- synchronous SQLite engine and session factories;
- explicit transaction context management;
- foreign-key enforcement;
- UTC-safe datetime storage;
- Alembic configuration and one reviewed initial migration.

It intentionally contains no repository operations, persistence DTOs, import
save workflow, version-increment algorithm, idempotency decision logic, or CLI
database commands.

## Database configuration

`create_database_engine()` accepts a configurable SQLite URL and rejects other
database backends. `database_url_from_path()` safely converts a local path into
a SQLAlchemy URL. The default points to the ignored local path:

```text
data/reinaluxe-recovery.db
```

Creating an engine does not create that file until a connection is opened.
Every connection enables `PRAGMA foreign_keys=ON`. Database access is
synchronous and uses non-deprecated SQLAlchemy 2.x APIs.

`create_session_factory()` creates explicit sessions.
`transactional_session()` commits a successful unit of work and rolls back the
active transaction when an exception escapes. Business persistence behavior
will be layered above this boundary in Stage 004B.

## Migrations

Alembic reads the ORM `Base.metadata`. The configured URL can be supplied in
`alembic.ini`, overridden by an Alembic `Config`, or provided through the
`REINALUXE_DATABASE_URL` environment variable. No credentials are stored in
the repository.

The initial revision `20260714_0001` creates all four persistence tables,
constraints, indexes, string-backed enums, and conservative foreign keys. Its
downgrade removes the circular current-version reference first and then drops
tables in dependency-safe order.

No command in Stage 004A initializes the default local database. Migration
execution is exercised only against temporary SQLite files in tests.

## Boundary rules

- ORM instances stay inside the persistence package.
- ORM models do not inherit from Pydantic models.
- Validated domain payloads are stored as JSON without redefining domain
  semantics.
- No network or cloud database capability exists.
- No local database file belongs in Git.
