# Driver Employment and Payroll — Business Module Brief

STATUS: APPROVED

MODULE_ID: driver_employment_payroll

## Module identity

Private employment and payroll information shown only inside a selected driver
profile; it is not a new top-level navigation module.

## Business problem

The owner needs payroll facts connected to operational drivers without exposing
private employee data or inventing the meanings of source CSV columns.

## Facts

- FACT: The owner approved a private Employment/Payroll segment linked to each
  driver.
- FACT: The source data headings include employment type, basic salary, CPF
  rate, levy amount, allowance and status.
- FACT: The owner wants to choose a local/PR CPF category or a foreign-worker
  levy category for each worker.
- FACT: The first version records either the actual employer CPF amount or the
  actual foreign-worker levy amount manually and does not calculate it.
- FACT: Allowance is additional incentive pay from the company to the worker.
- FACT: The inspected private employee workbook has no Date of Birth or Age
  field and identifies the covered group as local employees, comprising
  Singapore citizens and Permanent Residents.
- FACT: Official CPF contribution rates vary by age, wage and citizenship or
  Permanent Resident year; a flat 17% formula is not universally correct.
- FACT: Real employee and payroll values must never be stored in GitHub.

## Required fields

Approved first-slice fields are a worker category, monthly basic salary in SGD,
employer CPF amount, foreign-worker levy amount, monthly incentive allowance in
SGD, effective month and employment status. CPF and levy are mutually exclusive:
the local/PR category permits employer CPF and the foreign-worker-with-levy
category permits levy. Employment status is separate from the driver's
operational availability.

## Reference sources

The owner's private July 2026 driver file, the inspected private employee
workbook and later owner-confirmed employment records are the sources. They
remain local and are not copied into Git. CPF rules must be checked against CPF
Board sources and levy treatment against Ministry of Manpower sources at the
time of use.

## Calculations

No calculation is approved. The owner enters the actual employer CPF amount or
monthly levy amount. The application must not multiply salary by 17%, derive age
from an identifier, calculate employee CPF deductions, infer levy tiers or
calculate gross pay.

## Workflows and approvals

The selected driver may show a private Employment/Payroll segment. Selecting
local/PR permits employer CPF entry and clears or disables levy entry. Selecting
foreign worker with levy permits levy entry and clears or disables CPF entry.
Both must never be active for the same effective record. Import remains
preview-first and separately approved. A changed amount or employment status
creates a new effective-month record rather than overwriting history.

## Imports

No import is approved. A later preview must redact sensitive values from logs and
must not send any row to an external AI worker.

## Reports and filters

No payroll report or cross-driver salary view is approved. The intended first
surface is the selected-driver private detail segment showing only the approved
category, monthly SGD amounts, current employment status and effective history.

## Database impact

A later proposal may add an employment/payroll history table linked to Driver.
Any structure must be additive, remain local, preserve existing drivers and use
an Alembic migration. Approval of this brief does not apply a migration.

## Security and compliance

Employment and payroll values are personal and financially sensitive. Until
authentication is implemented, the surface remains local and single-owner.
Singapore employment, CPF, levy and tax meanings require owner or professional
verification and cannot be created by AI assumption. In 2026 the 17% CPF rate is
only the employer share for certain full-rate employees aged 55 and below and
above the relevant wage band; other age, wage and PR-year cases differ. Foreign
worker levy is an employer cost and must not be deducted from a worker's salary.

## Owner decisions

None

## Acceptance examples

- Normal: an approved private field is shown only inside the selected driver.
- Normal: a local/PR worker has an owner-entered employer CPF amount and no levy
  amount.
- Normal: a levy-liable foreign worker has an owner-entered monthly levy amount
  and no CPF amount.
- Normal: a salary or allowance change creates a new effective-month record and
  leaves the earlier record readable.
- Normal: changing employment status does not change operational driver
  availability.
- Boundary: a missing approved value displays as not recorded, never zero.
- Boundary: the absence of birth date prevents automatic CPF calculation but
  does not prevent recording an actual paid CPF amount.
- Invalid: the same employment record contains both CPF and levy amounts.
- Invalid: AdvanCore applies 17% automatically without the required age, wage
  and citizenship/PR-year facts.
- Invalid: a worker attempts to place a real salary in a fixture or Git-tracked
  file and the change is rejected.
