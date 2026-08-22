# TASK-004 — Persistence / Service Architecture Foundation

STATUS: READY

## Objective
Establish a small, explicit persistence and service-layer foundation for AdvanCore so future business modules do not access SQLAlchemy directly from Streamlit pages or create inconsistent database/session patterns.

## Business context
TASK-001 identified that AdvanCore currently has only a minimal database service and no repository/service abstraction. TASK-002 established baseline tests. TASK-003 established Alembic migrations. Before real ERP modules proliferate, AdvanCore needs one consistent pattern for database session lifecycle, persistence access, and business-service boundaries.

This task must remain deliberately small. It is a foundation task, not an ERP feature task and not a generic enterprise framework build.

## Facts
- The current application is an early Python/Streamlit foundation.
- SQLAlchemy 2.x models already exist for Project, KnowledgeItem, ActivityLog, and SystemSetting.
- `advancore/services/database.py` currently owns a module-level engine, a read-only connectivity check, and `initialize_database()` using `Base.metadata.create_all()`.
- Alembic is now the approved migration framework for schema evolution.
- Existing UI pages other than Dashboard are placeholders and do not yet contain business persistence logic.
- There is currently no repository package, session factory abstraction, unit-of-work abstraction, or documented service/repository convention.

## Architectural intent
Use a simple layered direction:

`Streamlit page / UI -> application service -> repository -> SQLAlchemy session -> PostgreSQL`

Responsibilities should remain explicit:
- UI/pages: presentation, input/output, calling application services.
- Services: use-case orchestration and future business-rule coordination.
- Repositories: persistence queries and entity storage only.
- Database/session layer: engine and session lifecycle only.
- Alembic: schema creation/evolution history.

Do not introduce extra layers unless the existing repository proves they are required.

## In scope
1. Inspect the current database service, models, tests, and page imports before editing.
2. Add a SQLAlchemy 2.x session factory using the existing engine.
3. Provide a safe, explicit session lifecycle helper/context manager that:
   - opens a session,
   - commits on successful write completion where appropriate,
   - rolls back on exceptions,
   - always closes the session.
4. Create a small `advancore/repositories/` package.
5. Implement a minimal repository pattern against existing models sufficient to prove the architecture without expanding into all future domains.
6. Prefer concrete, understandable repositories over a large generic CRUD framework.
7. At minimum, provide repository support for `Project` and `KnowledgeItem`, including only basic operations needed to demonstrate the pattern, such as:
   - get by id,
   - list,
   - add,
   - and one natural lookup where useful (for example Project by name).
8. Create a small application-service layer demonstrating how future UI code should call repositories without embedding SQLAlchemy queries in pages.
9. At minimum, provide a `ProjectService` with a narrow set of operations that delegate persistence to the repository and do not invent new business rules.
10. Use dependency injection or constructor injection where practical so repositories/services can be tested without a live production database.
11. Add automated tests for session handling, repository behavior, and service delegation using isolated/disposable test infrastructure.
12. Document the approved layering and dependency direction in `docs/architecture/PERSISTENCE_SERVICE_ARCHITECTURE.md`.
13. Add an ADR documenting the chosen persistence/service convention under `docs/decisions/`.
14. Preserve all existing application behavior.
15. Produce the standard completion report.

## Out of scope
- New ERP/business entities.
- New database columns, tables, relationships, or Alembic revisions unless an unexpected unavoidable issue is discovered and separately reported for approval.
- Streamlit CRUD screens or UI feature development.
- Customer, route, fleet, payroll, finance, transport, contract, or compliance logic.
- A generic enterprise repository framework covering every possible model.
- CQRS, event sourcing, message buses, dependency-injection frameworks, async SQLAlchemy, or distributed architecture.
- Production deployment.
- Main-branch merge.
- Secrets handling changes.
- Commercial or compliance-rule changes.
- Broad refactoring outside the persistence/service boundary.
- Removing or changing `initialize_database()` / `Base.metadata.create_all()` behavior in this task. That Alembic-coexistence decision remains a separate controlled architecture decision unless implementation is impossible without resolving it.

## Database impact
No schema changes are expected.

Tests may use disposable SQLite databases or equivalent isolated test databases. Do not mutate production data. Do not run destructive commands against the development PostgreSQL database unless explicitly required for isolated validation and clearly safe.

## Acceptance criteria
- [ ] A SQLAlchemy session factory exists and uses the existing engine.
- [ ] Session lifecycle has deterministic commit/rollback/close behavior.
- [ ] `advancore/repositories/` exists with a small, explicit repository convention.
- [ ] Concrete repository support exists for Project and KnowledgeItem.
- [ ] A narrow `ProjectService` demonstrates the service boundary.
- [ ] Streamlit pages are not refactored into CRUD features as part of this task.
- [ ] No new business rules are invented.
- [ ] No database schema change or migration revision is introduced.
- [ ] Repository and service code can be tested without production credentials/data.
- [ ] Tests cover successful repository operations and at least one rollback/error path for session handling.
- [ ] Existing test suite remains passing.
- [ ] Architecture documentation and ADR are created.
- [ ] `git status --short` is reviewed and only TASK-004-related files are changed.
- [ ] Completion report is produced according to `AGENTS.md`.

## Test requirements
At minimum:

1. **Session lifecycle tests**
   - successful context closes the session;
   - exception path rolls back and closes;
   - no production database dependency.

2. **Project repository tests**
   - add and retrieve a Project using an isolated database/session;
   - list projects;
   - natural lookup if implemented.

3. **KnowledgeItem repository tests**
   - add and retrieve a KnowledgeItem using an isolated database/session;
   - list/filter only if implemented within the bounded scope.

4. **Project service tests**
   - verify the service delegates persistence through the repository boundary;
   - use a fake/mock repository where practical;
   - confirm the service does not require Streamlit or a live PostgreSQL connection.

5. Run the full suite:

`.venv/bin/python -m pytest tests/ -v`

Also run a Python compile/import sanity check for newly added modules.

## Constraints
- Read and obey `AGENTS.md` first.
- Work only on `agent-control-foundation`.
- Do not modify `main`.
- Do not merge anything.
- Do not commit or push until the owner/reviewer explicitly approves TASK-004 changes.
- Do not expose `.env` contents, credentials, or secrets.
- Keep the implementation small, explicit, reversible, and understandable.
- Prefer SQLAlchemy 2.x idioms.
- Do not allow repositories to contain presentation logic.
- Do not allow services to import Streamlit.
- Do not allow UI/pages to become the persistence abstraction.
- Do not duplicate engine creation in repositories/services.
- Do not introduce a second ORM or database library.
- Do not silently change the Alembic baseline.
- If the current `initialize_database()` / Alembic coexistence creates a real blocker, stop and report it instead of changing it outside scope.

## Owner decisions
None required to begin.

## Completion report
### Implemented

### Files changed

### Database changes

### Tests and results

### Assumptions

### Risks / unresolved issues

### Decisions required

### Recommended next step
