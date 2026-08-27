# TASK-119 — Fleet Identity and Current Cost Foundation

STATUS: READY

## Objective

Expand the existing truthful vehicle register into an owner-approved Fleet
foundation with registered-company grouping, exact LTA seating, bounded
logcard details, current parking/insurance/road-tax costs, and same-screen
filters and vehicle detail viewing.

## Business context

The existing vehicle register stores only registration number, make/model and
status. The owner has now reviewed 27 LTA vehicle documents and approved the
minimum operational fields needed to identify, group and inspect the fleet
without inventing finance, cost or compliance information.

## Facts

- The current register contains no legal-owner/company entity or detailed Fleet
  fields.
- Vehicles must be grouped and filtered by their registered owner/company.
- Vehicle type and exact LTA passenger capacity are separate filters.
- Approved vehicle types are Bus, lorry and car.
- Exact capacity must be stored; it must not be inferred from model wording or
  placed into an approximate seating band.
- Parking has no agreement record. Only current provider, location and monthly
  GST-inclusive cost are required.
- Insurance requires only the current provider and GST-inclusive annual amount.
- Road tax requires only the current amount and a 6- or 12-month selection.
  Local renewals are currently GIRO-paid, but the system must not infer an amount
  from seating capacity.
- Insurance, parking and road-tax history are not required.
- Diesel purchasing and workshop electric charging remain separate deferred
  designs.
- PC5234D is the confirmed registration number; its supplied PDF filename was
  incorrect.

## In scope

- Add a configurable registered-company/legal-owner entity with a unique name
  and active/inactive lifecycle.
- Extend vehicles with optional registered owner, manufacture year, exact LTA
  passenger capacity, vehicle type, propellant, and approved individual logcard
  detail fields: scheme, chassis number, engine number, original registration
  date, lifespan expiry, COE expiry, primary colour, unladen weight and maximum
  laden weight.
- Add current-only parking provider, parking location, GST-inclusive monthly
  parking cost, current insurance provider, GST-inclusive annual insurance
  amount, current road-tax amount and road-tax period months.
- Preserve unknown values as null and display them as not recorded.
- Extend the existing Fleet screen with separate company, vehicle-type and
  exact-seat filters, owner entry, bounded vehicle entry/update, and a selected
  vehicle detail view.
- Keep existing minimal vehicle creation and operational CSV publication
  compatible.
- Add one additive migration and isolated tests.

## Out of scope

- Importing any of the 27 real vehicles or copying personal/business source
  documents into the repository.
- Hire-purchase fields, remaining-payment calculations or official finance
  balances; these form a separate follow-on task.
- Parking agreements or historical parking, insurance or road-tax records.
- Diesel invoices, diesel analytics, workshop charging or a combined Energy
  module.
- Road-tax estimates or defaults based on capacity, including automatic use of
  S$850.
- Authentication, deployment, production, credentials, billing or `main`.

## Allowed changed-file scope

- `tasks/TASK-119-fleet-identity-current-cost-foundation.md`
- `advancore/models/legal_entity.py`
- `advancore/models/vehicle.py`
- `advancore/models/__init__.py`
- `advancore/repositories/legal_entity.py`
- `advancore/repositories/vehicle.py`
- `advancore/repositories/__init__.py`
- `advancore/services/legal_entity_service.py`
- `advancore/services/vehicle_service.py`
- `advancore/pages/operations.py`
- `alembic/versions/e2f119fleet2_fleet_identity_current_cost.py`
- `tests/test_legal_entity_service.py`
- `tests/test_vehicle_service.py`
- `tests/test_operations_page.py`
- `tests/test_models.py`
- `tests/test_migrations.py`

## Database impact

One additive `legal_entities` table and nullable additive columns on `vehicles`.
Existing vehicle rows and related route, trip, assignment and fuel references
remain valid. No live migration may be applied unless a fresh local backup is
created and independently verified first.

## Acceptance criteria

- [ ] Existing vehicle rows and minimal two-field creation remain compatible.
- [ ] Legal-owner/company names are bounded, normalized and unique.
- [ ] Vehicle type accepts only Bus, lorry or car when recorded.
- [ ] Passenger capacity is the exact positive LTA value and remains independent
      of vehicle type.
- [ ] Company, type and capacity filters can be combined on the same Fleet
      screen without mutating data.
- [ ] Unknown optional fields remain null and are shown truthfully.
- [ ] Current parking, insurance and road-tax amounts use non-negative decimal
      values without estimating missing amounts.
- [ ] Road-tax period accepts only 6 or 12 months when an amount is recorded.
- [ ] S$850 is never automatically assigned from capacity.
- [ ] A selected vehicle shows the approved individual logcard and current-cost
      details.
- [ ] No real fleet data, source PDFs or credentials are committed.
- [ ] A fresh verified local backup exists before the additive migration is
      applied to the live local database.
- [ ] Focused and full tests pass; `git diff --check` passes; independent review
      finds no unresolved issue.

## Test requirements

- Test company validation, duplicate handling, lifecycle and persistence.
- Test vehicle validation, nullable fields, exact-capacity behavior, current
  cost rules, filters and existing creation compatibility.
- Test migration lineage, nullable additions, constraints and non-destructive
  upgrade operations without touching the live database.
- Test Fleet screen empty, filtered, detail and failure states.
- Run focused tests and the full isolated suite.

## Constraints

- `agent_runner` remains the authority boundary and the worker cannot approve
  its own implementation.
- GitHub remains source of truth; publication may target only this feature
  branch and later `projects-lifecycle-recovery`, never `main`.
- Preserve all existing transport workflows and foreign-key identities.
- No fabricated operational, financial, tax or compliance data.
- Amount fields describe owner-entered GST-inclusive current amounts; they are
  not accounting or tax calculations.
- Do not store source-document images or unnecessary personal data.

## Owner decisions

None. The owner approved the business fields and filters on 27 August 2026.

## Completion report

### Implemented

### Files changed

### Database changes

### Tests and results

### Assumptions

### Risks / unresolved issues

### Decisions required

### Recommended next step
