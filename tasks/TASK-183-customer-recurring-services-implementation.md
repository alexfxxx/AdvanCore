# TASK-183 — Customer Recurring Services Implementation

STATUS: COMPLETE

## Objective

Implement the approved recurring customer service data contract, loopback API
and customer-profile editing surface using synthetic tests and an unapplied
additive migration.

## Business context

Recurring routes have fixed tender schedules and fixed monthly prices. They must
be managed under the selected customer without duplicating daily Trip rows or
creating another top-level module.

## Facts

- The approved brief is
  `tasks/module-briefs/customer-recurring-services.md`.
- The approved schema proposal is TASK-181.
- Monthly prices are saved facts and have no daily or per-trip calculation.
- Actual customer source files and values never enter GitHub.

## In scope

- Add `RecurringService`, `RecurringServiceDay` and `RecurringServiceStop`
  models and one additive Alembic migration chained from `f3e166fleet3`.
- Add repositories and a service for create, list-by-customer, pause, archive
  and forward replacement.
- Validate customer/route existence, weekday uniqueness, stop order, effective
  dates, currency, non-negative monthly amount and allowed lifecycle states.
- Add nested read/write schemas and loopback-only confirmed API routes.
- Add a selected-customer Recurring Services view and confirmed editing controls
  to the existing primary-console Customers manager.
- Add synthetic focused tests.

## Out of scope

- Applying the migration or writing/importing any real record.
- Daily Trip generation, invoicing, GST, discounts, public-holiday rules,
  geocoding, mileage or profitability.
- Editing an active service's tender facts in place; use forward replacement.
- A new top-level module, Streamlit expansion, deployment, credentials or `main`.

## Allowed changed-file scope

- `tasks/TASK-181-customer-recurring-services-schema-proposal.md`
- `tasks/TASK-183-customer-recurring-services-implementation.md`
- `tasks/module-briefs/customer-recurring-services.md`
- `alembic/versions/f4e183recurring_customer_services.py`
- `advancore/models/__init__.py`
- `advancore/models/recurring_service.py`
- `advancore/repositories/__init__.py`
- `advancore/repositories/recurring_service.py`
- `advancore/services/recurring_service_service.py`
- `advancore/api/app.py`
- `advancore/api/dependencies.py`
- `advancore/api/editing_gateway.py`
- `advancore/api/routes/editing.py`
- `advancore/api/routes/operations.py`
- `advancore/api/schemas.py`
- `frontend/editing.js`
- `tests/test_recurring_service_service.py`
- `tests/test_api_recurring_services.py`
- `tests/test_frontend_editing_contract.py`

## Database impact

One additive migration is created but not applied. It creates the three approved
tables and leaves all existing tables and rows unchanged.

## Acceptance criteria

- [x] Recurring services are listed under one selected customer.
- [x] Creation writes the service, unique weekdays and ordered timed stops in
      one transaction.
- [x] Monthly amount is displayed exactly as entered and is never prorated.
- [x] Pause and archive do not delete history.
- [x] Replacement archives the prior version and links the new version.
- [x] All browser writes require loopback origin, action token and explicit
      confirmation.
- [x] No real customer value appears in code, tests, logs or Git.
- [x] Focused and surrounding tests pass; full regression remains part of the
      combined TASK-183/TASK-185 quality gate before publication.

## Test requirements

Use SQLite and synthetic records to test validation, nested persistence,
transaction rollback, forward replacement, API authorization and serialization.
Run focused tests, full pytest and `git diff --check`.

## Constraints

- `agent_runner` remains the authority boundary.
- GitHub stores code/schema only; PostgreSQL stores operational values.
- Migration application and real-data import require fresh owner approval.
- Worker may not stage, commit, push, merge, switch branches, access credentials
  or broaden scope.

## Module design gate

Classification: BUSINESS_MODULE
Module identifier: customer_recurring_services
Approved brief: tasks/module-briefs/customer-recurring-services.md

## Owner decisions

None

## Completion report

### Implemented

- Added normalized recurring service, weekday and ordered-stop persistence.
- Added fixed-monthly validation, lifecycle status and forward replacement.
- Added loopback read/write API contracts and activity events.
- Added Recurring Services inside the selected customer profile with no new
  top-level module.

### Files changed

- This task and its approved design records.
- Recurring service model, repository, service and additive migration.
- Shared API application, schemas, gateways and routes.
- Primary frontend manager and synthetic focused tests.

### Database changes

Created revision `f4e183recurring` chained from `f3e166fleet3`. It has not been
applied to any database.

### Tests and results

- Focused recurring service/API/frontend tests: 15 passed.
- Surrounding API, customer, route, repository, model and cutover tests: 44
  passed with an isolated SQLite `DATABASE_URL`.
- JavaScript syntax and final full regression are required before publication.

### Assumptions

Weekday values use `0` for Monday through `6` for Sunday, as explicitly exposed
by the API and UI.

### Risks / unresolved issues

Daily Trip generation remains deferred. The source-text vehicle requirement is
not interpreted as exact or minimum seating.

### Decisions required

Migration application and real-data import remain separate owner decisions.

### Recommended next step

Independent review, then prepare a PR into `projects-lifecycle-recovery`.
