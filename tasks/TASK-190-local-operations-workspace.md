# TASK-190 — Local operations workspace

## Approved scope

Replace the modal record manager with a permanent operations workspace and unify recurring services under the user-facing Routes concept. Add local registers for subcontractors, their drivers and vehicles, vehicle-linked maintenance, recurring-route assignment history, and management-accounting payment timing.

## Data boundary

- PostgreSQL remains the operational source of truth.
- Customer, contract, driver/payroll and assignment records remain on the operator's laptop.
- Git contains schema, migrations, application code, tests and documentation only.

## Accounting behavior

- Financial entries use an accounting/service month for management P&L.
- Expected and actual payment dates are optional.
- An unpaid entry without expected payment timing is floating and requires attention.
- Fixed subcontractor monthly costs are separate from future per-trip ad-hoc costs.

## Assignment invariants

- A recurring route has at most one active assignment.
- An assignment is either own fleet or subcontractor, never both.
- A subcontractor driver and vehicle must belong to the same active company.
- Replacement assignments start after the previous assignment and preserve non-overlapping history.

## Verification

Run migration, frontend contract, editing, daily operations, recurring-service and driver-employment tests using the project virtual environment.
