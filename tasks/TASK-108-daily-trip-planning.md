# TASK-108 — Daily Trip Planning Foundation

STATUS: APPROVED

## Objective
Add dated, owner-entered trip records linked to real routes.

## In scope
Unique trip reference, existing route, service date, manual planned/completed/cancelled status, additive migration, repository/service, tests.

## Explicitly out of scope
Invented schedules, GPS, automatic completion, live migration, production, deployment, or `main`.

## Allowed changed-file scope
- `advancore/models/trip.py`
- `advancore/models/__init__.py`
- `advancore/repositories/trip.py`
- `advancore/repositories/__init__.py`
- `advancore/services/trip_service.py`
- `alembic/versions/a8e108trip_daily_trips.py`
- `tests/test_trip_service.py`
- `tasks/TASK-108-daily-trip-planning.md`

## Database impact
One additive `trips` table, not applied live during implementation.

## Acceptance criteria
Only real routes may be selected; no fabricated trips; bounded status; no hard delete; tests and Bugbot clean.

## Test requirements
Focused trip/model/migration and full isolated regression.

## Constraints
Preserve governance; GitHub source of truth; merge only to development branch.

## Owner decisions
None; timings and customer linkage remain deferred.

## Completion report
Pending verification. Database migration prepared only. No decisions required.
