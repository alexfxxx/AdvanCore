# Persistence and Service Architecture

**Date:** 2026-08-20  
**Branch:** `agent-control-foundation`  
**Task:** TASK-004 — Persistence / Service Architecture Foundation

---

## 1. Purpose

This document defines the small, explicit persistence and service-layer
foundation for AdvanCore. It exists so future ERP modules do not access
SQLAlchemy directly from Streamlit pages and do not invent inconsistent
session or transaction patterns.

---

## 2. Approved layering

```
Streamlit page / UI
        │
        ▼
Application service  (use-case orchestration)
        │
        ▼
Repository           (persistence queries only)
        │
        ▼
SQLAlchemy session   (engine + lifecycle)
        │
        ▼
PostgreSQL
```

### Responsibility boundaries

| Layer | Owns | Must not own |
|-------|------|--------------|
| UI / pages (`advancore/pages/`) | Presentation, input/output, calling services | SQLAlchemy queries, direct database access |
| Application services (`advancore/services/`) | Use-case orchestration, future business-rule coordination | Presentation logic, ORM internals |
| Repositories (`advancore/repositories/`) | Persistence queries and entity storage | Business rules, presentation logic |
| Database layer (`advancore/services/database.py`) | Engine, session factory, session lifecycle | Business logic |
| Alembic (`alembic/`) | Schema creation and evolution history | Runtime data access |

---

## 3. Session lifecycle

The canonical way to obtain and dispose of a session is
`advancore.services.database.session_scope`:

```python
from advancore.services.database import session_scope
from advancore.repositories import ProjectRepository

with session_scope() as session:
    repo = ProjectRepository(session)
    project = repo.get_by_id(project_id)
```

`session_scope`:

- Opens a new `Session`.
- Yields it to the caller.
- Commits if the block exits successfully.
- Rolls back if the block raises an exception.
- Always closes the session in the `finally` block.

For tests or non-default engines, pass a custom session factory:

```python
from advancore.services.database import create_session_factory, session_scope

factory = create_session_factory(my_engine)
with session_scope(factory) as session:
    ...
```

---

## 4. Repository convention

- One repository module per major entity, under `advancore/repositories/`.
- Repositories are concrete and small. They expose only the operations needed
  by current use cases, not a generic CRUD framework.
- A repository receives its SQLAlchemy `Session` through the constructor.
- Repositories contain persistence logic only: no business rules, no
  presentation code, no Streamlit imports.

Current repositories:

- `ProjectRepository` — `get_by_id`, `list`, `add`, `get_by_name`.
- `KnowledgeItemRepository` — `get_by_id`, `list`, `add`, `list_by_project`.

---

## 5. Service convention

- Application services live under `advancore/services/`.
- Services receive repositories via constructor injection.
- Services orchestrate use cases and may validate inputs, but should not
  invent business rules outside approved scope.
- Services must not import Streamlit.

Current services:

- `ProjectService` — `create_project`, `get_project`, `find_project_by_name`,
  `list_projects`.

---

## 6. Testing approach

- Repository tests use an isolated in-memory SQLite database and a custom
  session factory.
- Service tests use fake or mock repositories so they do not require a live
  database or production credentials.
- Session tests verify commit/rollback behavior functionally and confirm the
  transaction is ended.

---

## 7. What is deliberately not included

- A generic enterprise repository framework.
- CQRS, event sourcing, message buses, async SQLAlchemy, or DI frameworks.
- Streamlit CRUD screens.
- New business entities, columns, tables, or migrations.
- Changes to `initialize_database()` or the existing module-level engine.

---

## 8. Reasoning labels

### FACT

- `advancore/services/database.py` owns the module-level engine and now also
  exposes `SessionLocal`, `create_session_factory`, and `session_scope`.
- `advancore/repositories/` contains `ProjectRepository` and
  `KnowledgeItemRepository`.
- `advancore/services/project_service.py` contains `ProjectService`.
- Tests use isolated SQLite databases and fake repositories.

### ASSUMPTION

- Future modules will follow the same layering unless a later task explicitly
  changes this convention.

### INFERENCE

- Keeping repositories concrete and small avoids over-engineering while still
  giving AdvanCore a consistent persistence boundary.
