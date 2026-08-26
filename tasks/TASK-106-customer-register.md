# TASK-106 — Customer Register Foundation

STATUS: APPROVED

## Objective
Add an empty-by-default customer register for later routes, trips, and financial records.

## In scope
Customer name, optional internal reference, active/inactive status, additive migration, Operations view, bounded activity actions, and isolated tests.

## Explicitly out of scope
Contacts, payment data, contracts, identity documents, sample data, live migration, authentication, deployment, production, or `main`.

## Allowed changed-file scope
- `advancore/models/customer.py`
- `advancore/models/__init__.py`
- `advancore/repositories/customer.py`
- `advancore/repositories/__init__.py`
- `advancore/services/customer_service.py`
- `advancore/services/activity_service.py`
- `advancore/pages/operations.py`
- `alembic/versions/e6e106cust_customer_register.py`
- `tests/test_customer_service.py`
- `tests/test_activity_service.py`
- `tests/test_models.py`
- `tests/test_operations_page.py`
- `tasks/TASK-106-customer-register.md`

## Database impact
One additive `customers` table, not applied live during implementation.

## Acceptance criteria
No fabricated data; bounded validation and uniqueness; no hard delete; minimal activity; all tests and Bugbot clean.

## Test requirements
Focused domain/model/activity/page/migration checks and full isolated regression.

## Constraints
GitHub source of truth; preserve governance; merge only to `projects-lifecycle-recovery`.

## Owner decisions
None; sensitive/commercial fields remain deferred.

## Completion report
### Implemented
Added the customer register, lifecycle control, migration, Operations view, and bounded activity actions.
### Files changed
Customer model/repository/service, exports, Operations page, activity policy, migration, tests, and task record.
### Database changes
Additive migration prepared only.
### Tests and results
Focused checks: 44 passed. Full isolated suite: 1,153 passed and 2 PostgreSQL-only skips. Bugbot: clean. Whitespace: passed.
### Assumptions
The reference is an optional internal identifier.
### Risks / unresolved issues
None identified in independent review.
### Decisions required
None.
### Recommended next step
Verify and publish only to the development branch.
