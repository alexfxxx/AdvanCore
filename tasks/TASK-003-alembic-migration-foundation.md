# TASK-003 — Alembic Migration Foundation

STATUS: READY

## Objective
Introduce a controlled Alembic migration framework for AdvanCore so future database schema changes are versioned, reviewable, and reversible instead of relying only on `Base.metadata.create_all()`.

## Business context
AdvanCore is moving toward agent-assisted development and significant future schema growth. TASK-001 identified the lack of a migration framework as a structural risk. TASK-002 established a basic testing foundation. Before new ERP entities are added, database evolution must be governed through explicit migrations.

## Facts
- The project uses SQLAlchemy 2.x models under `advancore/models/`.
- The target database is PostgreSQL through `DATABASE_URL`.
- `advancore/services/database.py` currently exposes `initialize_database()` using `Base.metadata.create_all()`.
- Existing models include Project, KnowledgeItem, ActivityLog, and SystemSetting.
- Baseline tests now exist and must remain passing.
- No production deployment is part of this task.

## In scope
- Add Alembic as a project dependency.
- Initialize an Alembic configuration appropriate for this repository.
- Configure Alembic to obtain the database URL from the existing environment/config pattern rather than hard-coding credentials.
- Configure Alembic metadata discovery from `advancore.models.Base.metadata`.
- Create a baseline migration representing the current existing schema only.
- Document the approved migration workflow for future agents/developers.
- Add or update tests/validation needed to verify migration configuration without modifying production data.
- Preserve current application behavior.

## Out of scope
- Adding new business entities or ERP modules.
- Changing existing model fields unless strictly required to make the migration system accurately represent the current schema and such change is separately identified for approval before implementation.
- Dropping tables or columns.
- Running destructive migrations against any production database.
- Reading or exposing `.env` contents.
- Replacing PostgreSQL with another database.
- Refactoring unrelated application code.
- Deployment or merge to `main`.

## Database impact
Migration infrastructure will be introduced. A baseline revision may create the existing AdvanCore tables when applied to an empty database. This task must not delete or mutate existing production data.

## Acceptance criteria
- [ ] Alembic is added to project dependencies.
- [ ] Repository contains a working Alembic configuration and migration directory.
- [ ] Alembic reads `DATABASE_URL` securely through the existing environment pattern; no credentials are committed.
- [ ] Alembic `target_metadata` points to the current AdvanCore SQLAlchemy metadata.
- [ ] A baseline migration exists for the current model schema only.
- [ ] Baseline migration contains no unexpected destructive operations.
- [ ] `alembic current`, `alembic heads`, or equivalent safe validation commands work in the local development environment where practical.
- [ ] Existing pytest suite still passes.
- [ ] Migration workflow is documented in README or architecture documentation.
- [ ] No production application behavior changes.
- [ ] Completion report produced.

## Test requirements
At minimum:
- Run the full existing pytest suite.
- Validate Alembic configuration imports successfully.
- Validate that Alembic can discover the current metadata.
- Inspect the generated baseline migration for expected tables and absence of destructive operations.
- If practical, validate upgrade/downgrade against a disposable local/test database only. Do not use production data.

## Constraints
- Follow `AGENTS.md`.
- Stay on `agent-control-foundation`.
- Do not modify `main`.
- Do not expose secrets or `.env` contents.
- Prefer small, reversible changes.
- Do not remove `initialize_database()` in this task unless explicitly required and approved; the goal is migration foundation, not broader service refactoring.
- If current database state conflicts with the proposed baseline migration, stop and report the conflict rather than forcing or stamping blindly.

## Owner decisions
None expected unless a conflict is discovered between the current live/local database state and the generated baseline schema.

## Completion report
### Implemented
- Added `alembic>=1.13,<2.0` to project dependencies and installed it in the local virtual environment.
- Initialized Alembic configuration (`alembic.ini`, `alembic/env.py`, `alembic/versions/`, `alembic/script.py.mako`, `alembic/README`).
- Configured `alembic/env.py` to read `DATABASE_URL` from the environment via `python-dotenv` and to set `target_metadata = advancore.models.Base.metadata`.
- Removed the placeholder database URL from `alembic.ini` so credentials cannot be committed accidentally.
- Generated baseline migration `alembic/versions/639d8b65223c_baseline.py` representing the current schema (`activity_logs`, `projects`, `system_settings`, `knowledge_items`).
- Added isolated migration validation tests in `tests/test_migrations.py`.
- Documented the migration workflow in `docs/architecture/MIGRATIONS.md` and recorded the decision in `docs/decisions/ADR-001-alembic-migration-framework.md`.
- Updated `README.md` with a migrations section.
- Preserved existing `initialize_database()` and application behavior.

### Files changed
- `requirements.txt`
- `README.md`
- `alembic.ini` (new)
- `alembic/env.py` (new)
- `alembic/README` (new)
- `alembic/script.py.mako` (new)
- `alembic/versions/639d8b65223c_baseline.py` (new)
- `tests/test_migrations.py` (new)
- `docs/architecture/MIGRATIONS.md` (new)
- `docs/decisions/ADR-001-alembic-migration-framework.md` (new)

### Database changes
- No production database was modified.
- Migration infrastructure introduced only. The baseline revision, when applied to an empty database, creates the four existing tables.
- The local Docker Compose development database (previously created via `Base.metadata.create_all()`) was verified to have schema parity with the baseline migration and then stamped at revision `639d8b65223c`. No tables, columns, or data were modified during stamping.

### Tests and results
- Full pytest suite: **8 passed** (existing 4 + new 4 migration tests).
- Validated `alembic heads`, `alembic current`, `alembic upgrade head`, and `alembic downgrade base` against a disposable SQLite database; all commands executed successfully.
- Validated against the Docker Compose PostgreSQL development database:
  - Schema parity check: **PASS**
  - `alembic stamp head`: **PASS**
  - `alembic current`: **639d8b65223c (head)**
  - `alembic upgrade head`: **PASS** (no-op)

### Assumptions
- The current SQLAlchemy models in `advancore/models/` are the authoritative representation of the schema to baseline.
- Future structural changes will be implemented through additional Alembic revisions rather than `Base.metadata.create_all()`.

### Risks / unresolved issues
- `initialize_database()` still uses `Base.metadata.create_all()`. A future task should define how bootstrapping coexists with migrations (e.g., stamp then upgrade, or remove `create_all`).

### Decisions required
- None at this time.

### Recommended next step
- Decide whether to update `initialize_database()` to use Alembic or to require migrations for schema setup, and update the legacy-database adoption procedure documented in `docs/architecture/MIGRATIONS.md` as needed.
