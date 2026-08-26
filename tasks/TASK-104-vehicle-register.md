# TASK-104 — Vehicle Register Foundation

STATUS: APPROVED

## Objective

Add a truthful, owner-entered vehicle register as the first transport-operations foundation.

## Business context

AdvanCore cannot support routes, trips, assignments, fuel, or financial analysis until real fleet records exist. The app must begin empty and never invent vehicles or operational figures.

## Facts

- The app is local and currently has no transport-domain tables.
- The owner approved implementation through TASK-111.
- Login remains deferred; `main`, production, credentials, and billing remain protected.

## In scope

- Add an additive vehicles table and migration.
- Register unique vehicle numbers with optional make/model.
- Support active, out-of-service, and retired lifecycle states without deletion.
- Add a light Transport Operations page and minimal Activity Log events.
- Add isolated tests.

## Explicitly out of scope

- Telematics, GPS, maintenance, compliance rules, sample data, or automated status changes.
- Live database migration during implementation.
- Authentication, deployment, production, or `main`.

## Allowed changed-file scope

- `advancore/models/vehicle.py`
- `advancore/models/__init__.py`
- `advancore/repositories/vehicle.py`
- `advancore/repositories/__init__.py`
- `advancore/services/vehicle_service.py`
- `advancore/services/activity_service.py`
- `advancore/pages/operations.py`
- `app.py`
- `alembic/versions/c4e104fleet1_vehicle_register.py`
- `tests/test_vehicle_service.py`
- `tests/test_operations_page.py`
- `tests/test_models.py`
- `tests/test_activity_service.py`
- `tasks/TASK-104-vehicle-register.md`

## Database impact

One additive `vehicles` table. No existing table or row is changed during implementation.

## Acceptance criteria

- The app starts with an empty vehicle register and no fabricated data.
- Registration numbers are normalized, unique, and bounded.
- Invalid status and database constraint violations fail closed.
- Records are never hard-deleted.
- Activity events contain only action, entity type, and identifier.
- Focused and full tests pass; Bugbot is clean.

## Test requirements

- Test validation, duplicate handling, persistence, listing, status changes, and database constraint.
- Run model and application smoke tests plus the full isolated suite.

## Constraints

- `agent_runner` and existing approval boundaries remain unchanged.
- No live data migration until final reviewed rebuild.
- GitHub is source of truth; merge only to `projects-lifecycle-recovery`.

## Owner decisions

None. Detailed fleet/compliance fields are deliberately deferred.

## Completion report

### Implemented

- Added an empty-by-default vehicle register, lifecycle status updates, and a
  light Transport Operations page.
- Added bounded validation, unique registration handling, additive migration,
  and minimal non-descriptive Activity Log events.

### Files changed

- Vehicle model, repository, service, Operations page, app navigation,
  migration, exports, tests, and this governed task specification.

### Database changes

Additive migration prepared; not applied to the live database.

### Tests and results

- Focused vehicle, Operations page, model, migration, and activity tests after
  repair: 41 passed.
- Full isolated suite: 1,144 passed and 2 PostgreSQL-only migration tests skipped.
- Repository whitespace validation: passed.

### Assumptions

Registration number is the only required initial vehicle identifier.

### Risks / unresolved issues

Bugbot's valid Activity Log policy finding was repaired. Final rerun: clean.

### Decisions required

None.

### Recommended next step

Verify, independently review, and publish only to `projects-lifecycle-recovery`.
