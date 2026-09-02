# TASK-181 — Customer Recurring Services Minimum Schema Proposal

STATUS: DRAFT

## Objective

Propose the smallest additive data contract required by the approved Customer
Recurring Services brief, without creating or applying a migration.

## Business context

One service definition must represent a repeating customer route and its fixed
monthly price while ordered timed stops and operating weekdays remain normalized
and queryable. Dated operational Trips remain separate.

## Facts

- The approved brief is
  `tasks/module-briefs/customer-recurring-services.md`.
- Existing Customers, Routes and dated Trips remain unchanged.
- Monthly pricing has no per-day or per-trip calculation.
- Real Eagles, TOS and other customer data must never enter GitHub.

## In scope

Review the following proposed additive structures:

- `recurring_services`: customer, route, service reference, source-text vehicle
  requirement, fixed monthly amount, currency, effective dates, status and an
  optional self-reference to the version replaced;
- `recurring_service_days`: one unique weekday row per service; and
- `recurring_service_stops`: ordered location and scheduled local time rows.

Review uniqueness, validation, version replacement, API and customer-profile
presentation implications using synthetic examples only.

## Out of scope

- Creating or applying an Alembic migration.
- Changing application code, importing data or committing source documents.
- Automatically generating dated Trips.
- Driver/vehicle assignment, invoicing, GST, service credits, profitability,
  geocoding, distance, mileage, passenger records or authentication.
- A new top-level module, deployment, credentials or `main`.

## Proposed database impact

A later additive migration would create three tables and foreign keys to
`customers`, `routes` and the optional replaced recurring-service row. Deleting
a referenced Customer or Route would be restricted. Monetary amounts would use
fixed precision and reject negative values. A service would require at least one
weekday and one stop before publication; the service, its days and stops would
be written in one transaction. Existing operational rows would remain unchanged.

No migration is authorised by this proposal.

## Proposed application impact

- Add a Recurring Services segment to the selected-customer profile.
- Keep the compact Customers register unchanged.
- Allow confirmed create, pause, archive and forward-replacement actions through
  the existing editing gateway and audit boundary.
- Keep actual Trip creation separate until a later generation policy is approved.
- Display only saved facts and use `Not recorded` only where the approved field
  is optional.

## Allowed changed-file scope

- `tasks/TASK-180-customer-recurring-services-business-brief.md`
- `tasks/TASK-181-customer-recurring-services-schema-proposal.md`
- `tasks/module-briefs/customer-recurring-services.md`

## Acceptance criteria

- [ ] Owner approves the exact proposed fields and three-table structure.
- [ ] Owner approves forward replacement instead of in-place commercial edits.
- [ ] No per-trip, per-day, tax or invoice calculation is introduced.
- [ ] Existing Customer, Route and Trip rows remain compatible and unchanged.
- [ ] Implementation and migration application remain separate approval gates.
- [ ] No real customer value or source file is added to GitHub.

## Test requirements

If implementation is approved, focused tests must cover required relationships,
weekday uniqueness, stop ordering, effective-date validation, non-negative fixed
monthly amounts, allowed statuses, transactional rollback, forward replacement,
API serialization, customer-profile display and rejection of out-of-scope input.
Tests use synthetic customer, route, schedule and price values only.

## Constraints

- The approved business brief is authoritative.
- `agent_runner` remains the authority boundary.
- Every later database change must be additive and created through Alembic.
- A fresh verified local backup is mandatory before applying a migration.
- No real-data publication may occur without a separate preview and approval.

## Module design gate

Classification: BUSINESS_MODULE
Module identifier: customer_recurring_services
Approved brief: tasks/module-briefs/customer-recurring-services.md

## Owner decisions

Approve, reject or amend this minimum schema proposal. No implementation or
migration is authorised until that decision is recorded.

## Completion report

### Implemented

Proposal only.

### Files changed

- This task file.

### Database changes

None.

### Tests and results

- Approved customer recurring-services brief: ready.
- TASK-181 business-module gate: passed against the approved brief.
- Focused module-design tests: 14 passed.
- `git diff --check`: passed.

### Assumptions

`vehicle_requirement` remains source text for the first slice so AdvanCore does
not invent an exact-versus-minimum seating rule.

### Risks / unresolved issues

Daily Trip generation remains deliberately deferred.

### Decisions required

Owner approval of this schema proposal.

### Recommended next step

Approve TASK-181 implementation planning while withholding migration application
and real-data import.
