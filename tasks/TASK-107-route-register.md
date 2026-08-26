# TASK-107 — Route Register Foundation

STATUS: APPROVED

## Objective
Add an empty, owner-entered route register for later trip planning.

## In scope
Unique route code, origin, destination, manual active/inactive status, additive migration, repository/service, and isolated tests.

## Explicitly out of scope
Maps, GPS, distance, travel-time estimates, pricing, sample data, live migration, deployment, production, or `main`.

## Allowed changed-file scope
- `advancore/models/route.py`
- `advancore/models/__init__.py`
- `advancore/repositories/route.py`
- `advancore/repositories/__init__.py`
- `advancore/services/route_service.py`
- `alembic/versions/f7e107route_route_register.py`
- `tests/test_route_service.py`
- `tests/test_models.py`
- `tasks/TASK-107-route-register.md`

## Database impact
One additive `routes` table, not applied live during implementation.

## Acceptance criteria
No fabricated data; bounded unique codes and locations; distinct origin/destination; no hard delete; tests and Bugbot clean.

## Test requirements
Focused model/service/migration checks and full isolated regression.

## Constraints
Preserve governance; GitHub source of truth; merge only to `projects-lifecycle-recovery`.

## Owner decisions
None; mapping and commercial rules remain deferred.

## Completion report
### Implemented
Added the bounded route model, repository, service, and migration.
### Files changed
Route model/repository/service, exports, migration, tests, and task record.
### Database changes
Additive migration prepared only.
### Tests and results
Focused: 19 passed. Full isolated: 1,155 passed and 2 PostgreSQL-only skips. Bugbot: clean. Whitespace: passed.
### Assumptions
Route code is an owner-defined internal identifier.
### Risks / unresolved issues
No issue identified; UI entry is intentionally deferred to the next operational presentation increment.
### Decisions required
None.
### Recommended next step
Verify and publish only to the development branch.
