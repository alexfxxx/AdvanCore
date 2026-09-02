# TASK-182 — Driver Employment and Payroll Business Brief

STATUS: DRAFT

## Objective

Define a private Employment/Payroll segment inside each driver profile without
inventing salary, CPF, levy or allowance meanings from the supplied CSV.

## Business context

The driver's operational identity and availability are already stored. The owner
also needs private employment and payroll facts linked to the same driver, but
the supplied July 2026 CSV contains sensitive values and ambiguous field
semantics that must be resolved before schema design or import.

## Facts

- The owner approved a private Employment/Payroll section linked to each driver.
- The source headings include employment type, basic salary, CPF rate, levy
  amount, allowance and status.
- Driver and payroll data must remain in local PostgreSQL and protected local
  backups and must never be committed to GitHub.
- Login and multi-user access controls are currently deferred.

## In scope

- Record confirmed requirements and unresolved meanings.
- Keep payroll inside the driver profile rather than creating unnecessary
  top-level navigation.
- Define the security and approval boundary for a later schema proposal.

## Out of scope

- Models, migration, application code, calculations or import.
- Copying any driver name, employee reference or payroll amount into Git.
- CPF, levy, tax, payslip or statutory compliance rules.
- Authentication, payroll processing, bank files, deployment or `main`.

## Database impact

None.

## Allowed changed-file scope

- `tasks/TASK-182-driver-employment-payroll-business-brief.md`
- `tasks/module-briefs/driver-employment-payroll.md`

## Acceptance criteria

- [ ] Every payroll source heading has an owner-confirmed meaning and unit.
- [ ] Effective-date and history behavior is approved.
- [ ] Private visibility and local-only storage boundaries are approved.
- [ ] No real driver or payroll value is committed or imported.
- [ ] A later schema proposal contains no unapproved fields.

## Test requirements

- Evaluate the draft brief and confirm that unresolved decisions fail closed.
- Run focused module-design tests and `git diff --check`.

## Constraints

- The CSV is reference data, not authority to infer business rules.
- No payroll value may be sent to Kimi, Gemini, Codex or another external worker.
- Synthetic values only may appear in tests.
- A fresh verified backup and explicit migration approval are mandatory before
  any later local schema activation.

## Module design gate

Classification: NON_MODULE
Module identifier: None
Approved brief: None

## Owner decisions

Confirm the allowed employment types; whether `cpf_rate` means employer,
employee or another rate and whether it is stored or calculated; whether levy
and allowance are fixed monthly values; whether salary is monthly SGD; whether
changes need effective dates and history; and whether the CSV status duplicates
the driver's operational status or represents employment status.

## Completion report

### Implemented

Drafted the private driver-profile payroll boundary without schema or data work.

### Files changed

- This task file.
- `tasks/module-briefs/driver-employment-payroll.md`.

### Database changes

None.

### Tests and results

- Draft payroll brief: correctly not implementation-ready while owner decisions
  remain unresolved.
- Focused module-design tests: 14 passed.
- `git diff --check`: passed.

### Assumptions

None.

### Risks / unresolved issues

Authentication is deferred, so private payroll visibility must remain local and
single-owner until access control is separately approved.

### Decisions required

The field meanings listed above.

### Recommended next step

Resolve the payroll meanings before proposing any table or migration.
