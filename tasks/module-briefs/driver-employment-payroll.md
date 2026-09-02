# Driver Employment and Payroll — Business Module Brief

STATUS: DRAFT

MODULE_ID: TODO

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
- FACT: Real employee and payroll values must never be stored in GitHub.

## Required fields

The source headings are candidates only until the owner confirms their exact
meaning, unit, allowed values and history behavior.

## Reference sources

The owner's private July 2026 driver file and later owner-confirmed employment
records are the sources. They remain local and are not copied into Git.

## Calculations

No calculation is approved. CPF, levy, allowance, gross pay and statutory
obligations must not be inferred.

## Workflows and approvals

Private view and edit controls may be proposed only after field meanings and
history rules are approved. Import remains preview-first and separately approved.

## Imports

No import is approved. A later preview must redact sensitive values from logs and
must not send any row to an external AI worker.

## Reports and filters

No payroll report or cross-driver salary view is approved. The intended first
surface is the selected-driver private detail segment.

## Database impact

None at the brief stage. Any later proposal must be additive and remain local.

## Security and compliance

Employment and payroll values are personal and financially sensitive. Until
authentication is implemented, the surface remains local and single-owner.
Singapore employment, CPF, levy and tax meanings require owner or professional
verification and cannot be created by AI assumption.

## Owner decisions

Confirm employment-type values; the meaning and treatment of CPF rate; the unit
and cadence of salary, levy and allowance; effective-date and history behavior;
and whether source status is operational driver status or employment status.

## Acceptance examples

- Normal: an approved private field is shown only inside the selected driver.
- Boundary: a missing approved value displays as not recorded, never zero.
- Invalid: a worker attempts to place a real salary in a fixture or Git-tracked
  file and the change is rejected.
