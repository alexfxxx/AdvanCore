# TASK-185 — Driver Employment and Payroll Implementation

STATUS: READY

## Objective

Implement the approved private effective-month employment/payroll history under
each driver profile using synthetic tests and an unapplied additive migration.

## Business context

The owner needs current and historical employer-cost facts linked to a driver,
with no statutory calculation and no effect on operational availability.

## Facts

- The approved business brief and schema proposal are authoritative.
- Salary and allowance are monthly SGD amounts.
- Employer CPF and foreign-worker levy are manual and mutually exclusive.
- No real employee or payroll record may enter GitHub.

## In scope

- Add `DriverEmploymentRecord` and one additive Alembic migration chained from
  TASK-183's revision.
- Add repository/service create and list-by-driver behavior with effective-month
  ordering and strict validation.
- Add read/write API schemas, loopback-only confirmed routes and a private
  Employment/Payroll segment in the selected-driver manager.
- Keep Driver operational status unchanged.
- Add synthetic focused tests.

## Out of scope

- Applying migrations or importing the supplied employee files.
- Automatic CPF/levy calculations, DOB, NRIC/FIN, nationality, work-pass data,
  employee CPF deductions, payroll runs, payslips, reports or bank details.
- Authentication, deployment, credentials or `main`.

## Allowed changed-file scope

- `tasks/TASK-182-driver-employment-payroll-business-brief.md`
- `tasks/TASK-184-driver-employment-payroll-schema-proposal.md`
- `tasks/TASK-185-driver-employment-payroll-implementation.md`
- `tasks/module-briefs/driver-employment-payroll.md`
- `alembic/versions/f5e185driver_employment_payroll.py`
- `advancore/models/__init__.py`
- `advancore/models/driver_employment.py`
- `advancore/repositories/__init__.py`
- `advancore/repositories/driver_employment.py`
- `advancore/services/driver_employment_service.py`
- `advancore/api/app.py`
- `advancore/api/dependencies.py`
- `advancore/api/editing_gateway.py`
- `advancore/api/routes/editing.py`
- `advancore/api/routes/operations.py`
- `advancore/api/schemas.py`
- `frontend/editing.js`
- `tests/test_driver_employment_service.py`
- `tests/test_api_driver_employment.py`
- `tests/test_frontend_editing_contract.py`

## Database impact

One additive migration is created but not applied. Existing driver and
operational records remain unchanged.

## Acceptance criteria

- [ ] Records list newest effective month first under the selected driver.
- [ ] Local/PR accepts employer CPF and rejects levy.
- [ ] Foreign-worker-with-levy accepts levy and rejects CPF.
- [ ] Salary, CPF, levy and allowance reject negative values.
- [ ] Employment status never mutates Driver status.
- [ ] Browser writes require loopback origin, action token and confirmation.
- [ ] No real employee value appears in code, tests, logs or Git.
- [ ] Relevant and full tests pass and completion evidence is recorded.

## Test requirements

Use SQLite and synthetic values. Run focused service/API/frontend tests, full
pytest and `git diff --check`.

## Constraints

- `agent_runner` remains the authority boundary.
- The primary console remains loopback-only.
- Migration application and real-data import require fresh owner approval.
- Worker may not stage, commit, push, merge, switch branches, access credentials
  or broaden scope.

## Module design gate

Classification: BUSINESS_MODULE
Module identifier: driver_employment_payroll
Approved brief: tasks/module-briefs/driver-employment-payroll.md

## Owner decisions

None

## Completion report

### Implemented

Pending.

### Files changed

Pending.

### Database changes

Migration created but not applied.

### Tests and results

Pending.

### Assumptions

None.

### Risks / unresolved issues

Authentication remains deferred; private values remain local and single-owner.

### Decisions required

Migration application and real-data import remain separate owner decisions.

### Recommended next step

Independent review, then include in the same bounded PR only if clean.
