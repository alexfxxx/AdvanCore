# TASK-002 — Testing Foundation

STATUS: READY

## Objective
Establish a minimal, reliable automated test foundation for the current AdvanCore codebase before any further ERP feature or architecture expansion.

## Business context
TASK-001 confirmed that AdvanCore currently has no real automated tests, `tests/_init_.py` is misnamed, and `pytest` is not installed in the project virtual environment. Before agents are allowed to make larger autonomous code changes, the repository needs a small baseline test suite that can detect obvious regressions in the existing foundation.

## Facts
- The current repository is an early AdvanCore platform foundation, not yet a full transport ERP.
- `tests/_init_.py` exists, is empty, and uses a non-standard package filename.
- `pytest` is not currently installed in `.venv`.
- The application uses Python, Streamlit, SQLAlchemy and PostgreSQL.
- Current ORM models include `Project`, `KnowledgeItem`, `ActivityLog`, and `SystemSetting`.
- `advancore/services/database.py` exposes database connectivity and initialization functions.
- TASK-001 found that schema creation currently relies on `Base.metadata.create_all()`; migration work is reserved for a later task.

## In scope
- Rename `tests/_init_.py` to `tests/__init__.py`.
- Add `pytest` to the project dependency list in the appropriate existing dependency file.
- Install `pytest` into the local `.venv` only as needed to execute and verify the task.
- Add a minimal baseline smoke-test suite covering the current foundation.
- Test that the public model package imports successfully.
- Test that the expected SQLAlchemy model tables are registered in `Base.metadata`.
- Add safe tests for database service behavior that do not modify production data and do not require destructive database operations.
- Prefer isolated/unit-style tests where practical; use mocking or monkeypatching when database environment dependencies would otherwise make tests unsafe or brittle.
- Run the completed test suite using `.venv/bin/python -m pytest`.
- Update documentation only where needed to record verified testing instructions or findings.

## Out of scope
- New ERP or business modules.
- Alembic or any other migration framework.
- Database schema changes.
- Model redesign or relationship changes.
- Repository/service architecture refactoring.
- Streamlit UI redesign.
- Production deployment or CI/CD setup.
- Production database writes, deletes, drops, resets, or migrations.
- Reading, printing, copying, or committing `.env` contents or secrets.
- Changing commercial, operational, or compliance business rules.
- Broad refactoring unrelated to making the existing foundation testable.

## Database impact
None. This task must not change the database schema or production data.

Tests may inspect SQLAlchemy metadata and may mock database connections. Any live database connectivity check must be read-only and limited to the existing safe `SELECT 1` behavior.

## Acceptance criteria
- [ ] `tests/_init_.py` no longer exists.
- [ ] `tests/__init__.py` exists.
- [ ] `pytest` is declared in the appropriate project dependency file.
- [ ] The project `.venv` can execute `python -m pytest` successfully.
- [ ] At least one smoke test verifies that `advancore.models` imports successfully.
- [ ] Tests verify that the expected existing model tables are present in `Base.metadata` without altering schema.
- [ ] Database service behavior has at least one safe automated test that does not require destructive database access.
- [ ] All tests added by this task pass using `.venv/bin/python -m pytest`.
- [ ] No application feature behavior, database schema, or production data is changed.
- [ ] `git status --short` is reviewed before completion and only task-related files are changed.
- [ ] Completion report is produced according to `AGENTS.md`.

## Test requirements
At minimum, create tests for:

1. **Model import smoke test**
   - Import `Base`, `Project`, `KnowledgeItem`, `ActivityLog`, and `SystemSetting` from `advancore.models`.
   - Confirm imports succeed.

2. **Metadata registration test**
   - Inspect `Base.metadata`.
   - Confirm the tables corresponding to the four existing models are registered.
   - Do not create or modify a database schema as part of this test.

3. **Database service test**
   - Verify a safe behavior of `advancore.services.database`.
   - Prefer mocking/monkeypatching the engine/connection so the automated test does not depend on production credentials or mutate any database.
   - If testing `test_database_connection()`, cover at least the successful read-only path or failure-handling path without exposing secrets.

Run:

`.venv/bin/python -m pytest tests/ -v`

Also run a Python compile/import sanity check for files modified by this task if useful.

## Constraints
- Read and obey `AGENTS.md` before starting.
- Remain on `agent-control-foundation` unless explicitly instructed otherwise by the owner.
- Do not modify `main` directly.
- Do not merge anything.
- Do not push or commit until the owner/reviewer explicitly authorises those actions for this task.
- Do not inspect or expose `.env` contents.
- Do not solve TASK-003 migration work during this task.
- Keep tests deterministic, small and understandable.
- Do not introduce a new testing framework when `pytest` is sufficient.
- Do not add unnecessary dependencies.
- If an existing design makes a safe test impossible without production coupling, stop and report the issue rather than redesigning the system outside scope.

## Owner decisions
None required to begin. The owner has approved establishing the testing foundation before further feature work.

## Completion report
### Implemented

### Files changed

### Database changes

### Tests and results

### Assumptions

### Risks / unresolved issues

### Decisions required

### Recommended next step
