# TASK-184 — Driver Employment and Payroll Minimum Schema Proposal

STATUS: COMPLETE

## Objective

Approve the smallest effective-month history structure for the approved private
Driver Employment/Payroll profile segment.

## Business context

The owner needs current employer cost facts and prior effective-month records
without storing date of birth, calculating CPF or mixing employment state with
operational driver availability.

## Facts

- The approved brief is
  `tasks/module-briefs/driver-employment-payroll.md`.
- Monthly basic salary and allowance use SGD.
- Employer CPF or foreign-worker levy is entered manually and mutually
  exclusive.
- Employment status is independent of Driver status.
- Real payroll values never enter GitHub.

## In scope

Approve one `driver_employment_records` history table with driver, effective
month, worker category, monthly basic salary, employer CPF amount, monthly levy
amount, monthly incentive allowance and employment status. Each driver may have
only one record per effective month.

## Out of scope

Date of birth, NRIC/FIN, nationality, work-pass identifiers, CPF rate, employee
CPF deduction, automatic CPF/levy calculation, gross pay, tax, payslips, bank
details, payroll runs, reports, import, authentication or deployment.

## Proposed database impact

One later additive Alembic migration creates `driver_employment_records` with a
restricting Driver foreign key, unique driver/effective-month pair, non-negative
money checks, worker-category and employment-status checks, and a mutual-
exclusion check for CPF versus levy. Existing Driver rows remain valid.

## Allowed changed-file scope

- `tasks/TASK-182-driver-employment-payroll-business-brief.md`
- `tasks/TASK-184-driver-employment-payroll-schema-proposal.md`
- `tasks/TASK-185-driver-employment-payroll-implementation.md`
- `tasks/module-briefs/driver-employment-payroll.md`

## Acceptance criteria

- [x] Owner approved monthly SGD salary and allowance.
- [x] Owner approved manual mutually exclusive CPF or levy amounts.
- [x] Owner approved effective-month history.
- [x] Owner approved separate employment and operational statuses.
- [x] No personal identifier or automatic statutory formula is proposed.
- [x] Migration application and data import remain separate approval gates.

## Test requirements

Implementation tests must use synthetic records and cover effective-month
uniqueness, non-negative money, category/cost mutual exclusion, independent
statuses, ordered history and transactional rollback.

## Constraints

- Sensitive values remain local in PostgreSQL and protected backups.
- GitHub contains only schema/code and synthetic fixtures.
- A fresh verified backup is required before any migration application.

## Module design gate

Classification: BUSINESS_MODULE
Module identifier: driver_employment_payroll
Approved brief: tasks/module-briefs/driver-employment-payroll.md

## Owner decisions

None

## Completion report

### Implemented

Recorded the owner-approved minimum history schema.

### Files changed

- This task file.
- TASK-182, TASK-185 and the approved module brief.

### Database changes

None. TASK-185 may create, but not apply, the migration.

### Tests and results

Pending documentation validation.

### Assumptions

An effective month is stored as the first calendar day of that month.

### Risks / unresolved issues

Authentication remains deferred; the surface remains loopback-only and
single-owner.

### Decisions required

None for the proposal.

### Recommended next step

Implement TASK-185 without applying its migration or importing employee data.
