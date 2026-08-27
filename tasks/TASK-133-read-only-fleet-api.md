# TASK-133 — Read-Only Fleet API

STATUS: READY

## Objective
Expose the existing approved Fleet register through rollback-only FastAPI read models.

## In scope
- Read existing registered companies and vehicles through current repositories/services.
- Return only existing model fields approved by TASK-119 and imported by TASK-124.
- Support company, vehicle-type, and exact-capacity filters.

## Out of scope
- Writes, imports, new columns, estimates, financial calculations, migrations, or sample data.

## Database impact
None; rollback-only reads.

## Allowed changed-file scope
- `advancore/api/**`
- `tests/test_api_fleet.py`
- `docs/architecture/DECOUPLED_LOCAL_CONSOLE.md`
- This task file

## Acceptance criteria
- [ ] API returns truthful existing Fleet values and nulls.
- [ ] Filters use approved exact values.
- [ ] No transaction can commit.
- [ ] Tests pass.

## Owner decisions
None; no field expansion is allowed.

## Completion report
Pending.
