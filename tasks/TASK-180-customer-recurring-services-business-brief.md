# TASK-180 — Customer Recurring Services Business Brief

STATUS: COMPLETE

## Objective

Define the minimum approved business boundary for recurring customer transport
services inside each customer profile, without creating another visible module or
turning recurring schedules into manually duplicated daily trips.

## Business context

The owner manages customer routes that repeat on agreed operating days for a
fixed monthly rate. The existing daily Trip register represents an actual
journey on a specific date and therefore cannot safely hold the source schedule
without repeated manual entry or loss of the tender-level meaning.

## Facts

- Customer routes repeat on the operating days agreed in the tender.
- Each recurring route has a fixed monthly price.
- The monthly price is not divided by trips, operating days or calendar days.
- The operating days remain fixed until the next agreement changes them.
- Ad-hoc services are separate one-off work.
- The owner wants recurring services visible and editable inside the customer
  profile, not in a separate top-level Contract module.

## In scope

- Produce an approved business-module brief for customer recurring services.
- Distinguish the tender-level recurring service from future dated Trip records.
- Define forward-only replacement when a new agreement changes a service.
- Preserve the source-stated monthly amount without calculating GST, invoices,
  daily rates or missed-trip deductions.

## Out of scope

- Models, repositories, services, APIs, frontend code or migrations.
- Applying a migration or writing any operational record.
- Importing any real customer source data.
- Daily-trip generation, driver or vehicle assignment, invoicing, GST treatment,
  public-holiday adjustments, service credits or payroll.
- A new top-level navigation module, deployment, credentials or `main`.

## Allowed changed-file scope

- `tasks/TASK-180-customer-recurring-services-business-brief.md`
- `tasks/TASK-181-customer-recurring-services-schema-proposal.md`
- `tasks/module-briefs/customer-recurring-services.md`
- `tasks/TASK-182-driver-employment-payroll-business-brief.md`
- `tasks/module-briefs/driver-employment-payroll.md`

## Database impact

None.

## Acceptance criteria

- [x] Recurring services remain inside the customer profile.
- [x] Fixed monthly pricing is not converted into a daily or per-trip rate.
- [x] Actual dated Trips remain distinct from recurring service definitions.
- [x] Ad-hoc work remains distinct from recurring services.
- [x] No real customer schedule, stop, price or personal record is committed.
- [x] No migration or operational write occurs.

## Test requirements

- Evaluate the approved module brief with the read-only module brief validator.
- Evaluate the TASK-180 non-module design gate.
- Run focused module-design tests and `git diff --check`.

## Constraints

- GitHub stores code and governed specifications, never real customer schedules
  or prices.
- PostgreSQL remains the operational-data source of truth.
- `agent_runner` remains the authority boundary.
- A later implementation must use an additive Alembic migration and synthetic
  test data only.
- Migration application and real-data import require separate owner approval.

## Module design gate

Classification: NON_MODULE
Module identifier: None
Approved brief: None

## Owner decisions

None for this design task.

## Completion report

### Implemented

- Recorded the approved recurring-service business boundary and prepared a
  separate minimum schema proposal for later review.

### Files changed

- This task file.
- `tasks/TASK-181-customer-recurring-services-schema-proposal.md`.
- `tasks/module-briefs/customer-recurring-services.md`.
- Driver employment/payroll discovery documents authorised alongside this work.

### Database changes

None.

### Tests and results

- Approved customer recurring-services brief: ready, with eight confirmed facts,
  every required section, no placeholders or duplicates and no unresolved owner
  decisions.
- TASK-180 non-module gate: passed.
- Focused module-design tests: 14 passed.
- `git diff --check`: passed.

### Assumptions

None. GST and invoicing behavior are deliberately outside this slice.

### Risks / unresolved issues

Implementation and migration approval remain separate boundaries.

### Decisions required

Review TASK-181 before authorising implementation or migration creation.

### Recommended next step

Approve or amend the minimum schema proposal, then implement it without applying
the migration or importing real customer data.
