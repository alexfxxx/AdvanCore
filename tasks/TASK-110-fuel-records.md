# TASK-110 — Fuel Record Foundation

STATUS: APPROVED

## Objective
Store immutable, owner-entered fuelling facts for real vehicles without inventing consumption or efficiency.

## In scope
Vehicle, calendar date, positive litres, optional non-negative total cost and odometer, exact decimals, additive migration, repository/service, and tests.

## Explicitly out of scope
Price estimates, efficiency predictions, telematics, receipt images, editing/deletion, live migration, deployment, production, or `main`.

## Allowed changed-file scope
- `advancore/models/fuel_entry.py`
- `advancore/models/__init__.py`
- `advancore/repositories/fuel_entry.py`
- `advancore/repositories/__init__.py`
- `advancore/services/fuel_entry_service.py`
- `alembic/versions/c0e110fuel_fuel_entries.py`
- `tests/test_fuel_entry_service.py`
- `tasks/TASK-110-fuel-records.md`

## Database impact
One additive `fuel_entries` table, not applied live during implementation.

## Acceptance criteria
Only real vehicles and explicit valid values are accepted; no calculated or fabricated figures; entries are immutable; tests and Bugbot clean.

## Test requirements
Focused decimal/date/vehicle/model/migration checks and full isolated regression.

## Constraints
Preserve governance; GitHub source of truth; merge only to `projects-lifecycle-recovery`.

## Owner decisions
None; currency and analytics remain deferred until business rules are confirmed.

## Completion report

- Implemented immutable fuel-entry model, repository, service, migration, and
  isolated tests without applying the migration live.
- Unsupported precision is rejected rather than silently rounded.
- Focused checks: 26 passed. Full isolated suite: 1,169 passed and 2
  PostgreSQL-only skips. Whitespace check: passed.
- Bugbot's precision finding was repaired; final rerun: clean.
- No decisions required; next step is non-main PR publication.
