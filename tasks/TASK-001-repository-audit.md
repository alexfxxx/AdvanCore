# TASK-001 — Repository Audit and Architecture Map

STATUS: READY

## Objective
Create an accurate architecture and repository map of the existing AdvanCore codebase without implementing new business features.

## Business context
AdvanCore will increasingly be developed with AI agents. Before agents are allowed to make larger changes, the repository needs a verified map of its structure, dependencies, database state, test coverage and technical risks.

## Facts
- The repository is an early Python/Streamlit foundation.
- PostgreSQL is the intended operational database.
- SQLAlchemy models already exist.
- GitHub is the source of truth for approved code and documentation.

## In scope
1. Inspect the complete repository.
2. Map important directories and files.
3. Identify frontend/UI architecture.
4. Identify service/backend architecture.
5. Identify database models and relationships.
6. Identify database initialization/migration approach.
7. Identify existing modules and their maturity.
8. Identify configuration/environment requirements.
9. Identify tests and obvious coverage gaps.
10. Identify duplicated, obsolete or suspicious code if found.
11. Identify security risks visible from the repository.
12. Recommend the smallest safe technical sequence for the next phase.
13. Create or update `docs/architecture/REPOSITORY_MAP.md`.
14. Update `CURRENT_STATE.md` only where verified findings materially improve it.

## Out of scope
- Building new ERP modules.
- Rewriting the application architecture.
- Changing database schema.
- Production deployment.
- Deleting files.
- Broad refactoring.
- Changing business or compliance rules.

## Database impact
None. This is an audit/documentation task.

## Acceptance criteria
- [ ] Repository structure is mapped.
- [ ] Current stack and module boundaries are documented.
- [ ] Existing models/database mechanism are documented.
- [ ] Test situation and gaps are documented.
- [ ] Key risks are separated into FACT / INFERENCE / PROPOSAL where relevant.
- [ ] No application functionality is intentionally changed.
- [ ] `docs/architecture/REPOSITORY_MAP.md` is created.
- [ ] Completion report is produced.

## Test requirements
Run existing tests or documented validation commands where practical. If they cannot run, record the exact reason and do not hide the failure.

## Constraints
- Read `AGENTS.md` first.
- Preserve working functionality.
- Do not introduce new dependencies unless necessary to perform validation, and do not persist them without approval.
- Never expose credentials or secrets in reports.

## Owner decisions
None required to begin the audit.

## Completion report
Follow the standard completion-report format in `AGENTS.md`.
