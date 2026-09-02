# TASK-182 — Driver Employment and Payroll Business Brief

STATUS: COMPLETE

## Objective

Define a private Employment/Payroll segment inside each driver profile without
inventing salary, CPF, levy or allowance meanings from the supplied CSV.

## Business context

The driver's operational identity and availability are already stored. The owner
also needs private employment and payroll facts linked to the same driver, but
the supplied private files contain sensitive values. The owner has now resolved
the worker-category, CPF/levy and allowance meanings, while payment cadence and
history behavior remain to be confirmed before schema design or import.

## Facts

- The owner approved a private Employment/Payroll section linked to each driver.
- The source headings include employment type, basic salary, CPF rate, levy
  amount, allowance and status.
- The owner wants a worker-category choice between local/PR employees who have
  CPF and foreign workers who have a monthly levy.
- The owner wants to enter the actual employer CPF amount or levy amount rather
  than require an automatic calculation in the first version.
- Allowance is additional incentive pay from the company to the worker.
- The private employee workbook contains no Date of Birth or Age field and
  identifies its covered group as local employees (Singapore citizens and PRs).
- Driver and payroll data must remain in local PostgreSQL and protected local
  backups and must never be committed to GitHub.
- Login and multi-user access controls are currently deferred.
- Official 2026 CPF rates vary by age, wage band and citizenship/PR status. The
  17% rate is the employer share only for the full-rate, age-55-and-below band
  above the relevant wage threshold; it is not a universal CPF formula.

## In scope

- Record confirmed requirements and unresolved meanings.
- Keep payroll inside the driver profile rather than creating unnecessary
  top-level navigation.
- Define mutually exclusive manual employer CPF and foreign-worker levy inputs.
- Define the security and approval boundary for a later schema proposal.

## Out of scope

- Models, migration, application code, calculations or import.
- Copying any driver name, employee reference or payroll amount into Git.
- CPF, levy, tax, payslip or statutory compliance rules.
- Automatic CPF or levy calculation, date-of-birth storage or PR-year logic.
- Authentication, payroll processing, bank files, deployment or `main`.

## Database impact

None.

## Allowed changed-file scope

- `tasks/TASK-182-driver-employment-payroll-business-brief.md`
- `tasks/module-briefs/driver-employment-payroll.md`

## Acceptance criteria

- [x] Every approved first-slice payroll field has an owner-confirmed meaning
      and unit.
- [x] Worker category selects either CPF or levy cost entry.
- [x] Allowance is confirmed as employer-paid incentive compensation.
- [x] Salary and allowance are monthly SGD amounts.
- [x] Changes preserve effective-month history.
- [x] Employment status remains separate from operational driver availability.
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

None.

## Completion report

### Implemented

Drafted the private driver-profile payroll boundary without schema or data work,
then recorded the owner's manual CPF-or-levy and incentive-allowance rules.

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

None for the business brief. A separate schema proposal and implementation task
remain governed boundaries.

### Recommended next step

Prepare the minimum schema proposal and implementation without applying a
migration or importing real employee data.
