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

### Files changed

### Database changes

### Tests and results

### Assumptions

### Risks / unresolved issues

### Decisions required

### Recommended next step
