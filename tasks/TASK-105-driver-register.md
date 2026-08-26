# TASK-105 — Driver Register Foundation

STATUS: APPROVED

## Objective
Add a minimal owner-entered driver register without collecting unnecessary personal data.

## Business context
Trips cannot be assigned truthfully until drivers exist as governed operational records.

## In scope
- Add driver model, repository, service, additive migration, Operations section, bounded activity actions, and tests.
- Store name, optional internal employee reference, and manual active/unavailable/retired status only.

## Explicitly out of scope
- Licence scans, contact details, biometrics, payroll, compliance decisions, sample data, or automated monitoring.
- Live migration, authentication, deployment, production, or `main`.

## Allowed changed-file scope
- `advancore/models/driver.py`
- `advancore/models/__init__.py`
- `advancore/repositories/driver.py`
- `advancore/repositories/__init__.py`
- `advancore/services/driver_service.py`
- `advancore/services/activity_service.py`
- `advancore/pages/operations.py`
- `alembic/versions/d5e105driver_driver_register.py`
- `tests/test_driver_service.py`
- `tests/test_activity_service.py`
- `tests/test_models.py`
- `tests/test_operations_page.py`
- `tasks/TASK-105-driver-register.md`

## Database impact
One additive `drivers` table; not applied to the live database during implementation.

## Acceptance criteria
- Empty-by-default register; no fabricated drivers.
- Bounded validation, unique optional reference, manual lifecycle, no delete.
- Minimal activity identifiers only.
- Focused/full tests pass and Bugbot is clean.

## Test requirements
Test create, list, status, invalid and duplicate inputs, page empty state, activity policy, models, migrations, and full regression.

## Constraints
Preserve governance and privacy; GitHub source of truth; merge only to `projects-lifecycle-recovery`.

## Owner decisions
None. Sensitive/compliance fields are deferred.

## Completion report
### Implemented
Added the minimal driver register, manual lifecycle, Operations view, migration, and bounded activity actions.
### Files changed
Driver model/repository/service, exports, Operations page, activity policy, migration, tests, and this task.
### Database changes
Additive migration prepared only.
### Tests and results
Focused checks: 41 passed. Full isolated suite: 1,148 passed and 2 PostgreSQL-only skips. Bugbot: clean. Whitespace check: passed.
### Assumptions
An internal reference is optional and not a government identifier.
### Risks / unresolved issues
None identified in independent review.
### Decisions required
None.
### Recommended next step
Verify and publish only to `projects-lifecycle-recovery`.
