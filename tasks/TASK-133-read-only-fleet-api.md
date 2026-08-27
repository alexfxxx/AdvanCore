# TASK-133 — Read-Only Fleet API

STATUS: COMPLETE

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
- [x] API returns truthful existing Fleet values and nulls.
- [x] Filters use approved exact values.
- [x] No transaction can commit.
- [x] Tests pass.

## Owner decisions
None; no field expansion is allowed.

## Completion report
Added `GET /api/fleet` through the existing legal-entity and vehicle services.
Company, approved vehicle-type and positive exact-capacity filters are bounded;
the database session always rolls back and closes. No write route, schema change
or sample record was added. Verified by the full suite on 28 August 2026.
