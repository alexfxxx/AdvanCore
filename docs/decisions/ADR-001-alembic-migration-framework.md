# ADR-001 — Adopt Alembic for Database Migrations

## Status

Approved and implemented as part of TASK-003.

## Context

AdvanCore uses SQLAlchemy 2.x models under `advancore/models/`. Before this
decision, schema creation was performed by `Base.metadata.create_all()` in
`advancore/services/database.py`. As the platform grows toward agent-assisted
development and additional ERP modules, unversioned schema creation creates
operational risk: schema drift between environments, irreversible changes, and
no reviewable history.

## Decision

Adopt [Alembic](https://alembic.sqlalchemy.org/) as the controlled migration
framework for PostgreSQL schema changes.

Key configuration choices:

- `DATABASE_URL` is read from the environment (via `python-dotenv` and `.env` in
  development) instead of being hard-coded in `alembic.ini`.
- `target_metadata` in `alembic/env.py` points to `advancore.models.Base.metadata`
  so autogenerate can discover model changes.
- Migration scripts live in `alembic/versions/`.

## Consequences

- Schema changes are versioned, reviewable, and reversible.
- New environments can be brought to the current schema with `alembic upgrade head`.
- Existing `initialize_database()` is preserved in this iteration to avoid
  broader service refactoring; future tasks may decide how it coexists with or
  delegates to migrations.
- Developers and agents must create migrations for structural changes instead of
  relying on `create_all()`.

## Alternatives considered

- Continue using `Base.metadata.create_all()` only. Rejected: it does not
  support incremental schema evolution or reversibility.
- Use raw SQL migration files managed manually. Rejected: higher maintenance
  burden and no autogenerate support from SQLAlchemy models.

## Compliance / risks

- No production data is touched by this decision itself; it introduces tooling
  only.
- Credentials must remain in environment variables; `alembic.ini` does not
  contain a real database URL.
