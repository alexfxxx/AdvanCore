# TASK-109 — Trip Assignment Foundation

STATUS: APPROVED

## Objective
Link one real planned trip to one active vehicle and one active driver.

## In scope
Additive assignment table, strict existing-resource checks, one immutable assignment record per trip, manual release, repository/service, and tests.

## Explicitly out of scope
Guessed availability, automatic dispatch, overlapping-time rules, deletion, live migration, deployment, production, or `main`.

## Allowed changed-file scope
- `advancore/models/trip_assignment.py`
- `advancore/models/__init__.py`
- `advancore/repositories/trip_assignment.py`
- `advancore/repositories/__init__.py`
- `advancore/services/trip_assignment_service.py`
- `alembic/versions/b9e109assign_trip_assignments.py`
- `tests/test_trip_assignment_service.py`
- `tasks/TASK-109-trip-assignments.md`

## Database impact
One additive `trip_assignments` table, not applied live during implementation.

## Acceptance criteria
Only planned trips and active resources are accepted; one record per trip; release is forward-only; no fabricated assignment; tests and Bugbot clean.

## Test requirements
Focused assignment/model/migration checks and full isolated regression.

## Constraints
Preserve governance; GitHub source of truth; merge only to `projects-lifecycle-recovery`.

## Owner decisions
None; time-overlap logic requires later scheduling detail.

## Completion report

- Implemented the additive assignment model, repository, service, migration,
  and isolated tests without applying the migration live.
- Focused checks: 19 passed. Full isolated suite: 1,160 passed and 2
  PostgreSQL-only skips. Repository whitespace check: passed.
- Bugbot branch review against `projects-lifecycle-recovery`: clean.
- No decisions required; next step is non-main PR publication.
