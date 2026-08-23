# ADR-002 — Adopt a Layered Persistence and Service Convention

## Status

Approved and implemented as part of TASK-004.

## Context

AdvanCore has four SQLAlchemy 2.x models and a single `database.py` module that
owns the engine and a connectivity check. Before this decision:

- There was no explicit session lifecycle abstraction.
- There was no repository or service layer.
- Future Streamlit pages would be likely to embed SQLAlchemy queries directly,
  leading to inconsistent patterns and difficult testing.

TASK-004 was chartered to establish a small, explicit foundation before real
ERP modules are built.

## Decision

Adopt a layered persistence and service convention:

```
UI / Streamlit page -> application service -> repository -> SQLAlchemy session -> PostgreSQL
```

Key choices:

1. **Session lifecycle** — `advancore.services.database.session_scope` is the
   canonical context manager for sessions. It commits on success, rolls back on
   exception, and always closes the session.
2. **Session factory injection** — `create_session_factory(engine)` lets tests
   and isolated contexts supply a non-production engine without touching the
   module-level engine.
3. **Concrete repositories** — `advancore/repositories/` contains small,
   entity-focused repositories that receive a `Session` via constructor
   injection. Repositories contain persistence logic only.
4. **Application services** — `advancore/services/` contains use-case services
   that receive repositories via constructor injection. Services must not import
   Streamlit.
5. **No generic framework** — The foundation is intentionally minimal. Extra
   layers (unit of work abstractions, CQRS, event sourcing, async drivers, DI
   frameworks) are out of scope until a concrete use case requires them.

## Consequences

- Future pages have a clear place to call for persistence: services.
- Repositories and services can be tested in isolation using SQLite or fakes.
- The codebase avoids a heavyweight framework while still enforcing a
  consistent direction.
- The existing `initialize_database()` and module-level engine are preserved,
  so current behavior is unchanged.

## Alternatives considered

- **Direct SQLAlchemy access from pages.** Rejected: it fragments persistence
  patterns and makes testing dependent on Streamlit and a live database.
- **Generic CRUD repository base class.** Rejected: it adds abstraction before
  AdvanCore has enough entities to justify it, and it encourages repositories
  to grow beyond bounded scope.
- **Unit-of-Work wrapper around repositories.** Rejected: the session scope is
  sufficient for the current foundation; a UoW can be introduced later if
  multi-repository transactions become common.

## Compliance / risks

- No production data is touched by this decision; it introduces code
  organization and helpers only.
- No schema changes or migrations were introduced.
- The convention must be followed by future tasks unless a later ADR revises
  it.
