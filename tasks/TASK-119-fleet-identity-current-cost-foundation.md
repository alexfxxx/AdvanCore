# TASK-119 — Fleet Identity and Current Cost Foundation

STATUS: APPROVED

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

- [x] Existing vehicle rows and minimal two-field creation remain compatible.
- [x] Legal-owner/company names are bounded, normalized and unique.
- [x] Vehicle type accepts only Bus, lorry or car when recorded.
- [x] Passenger capacity is the exact positive LTA value and remains independent
      of vehicle type.
- [x] Company, type and capacity filters can be combined on the same Fleet
      screen without mutating data.
- [x] Unknown optional fields remain null and are shown truthfully.
- [x] Current parking, insurance and road-tax amounts use non-negative decimal
      values without estimating missing amounts.
- [x] Road-tax period accepts only 6 or 12 months when an amount is recorded.
- [x] S$850 is never automatically assigned from capacity.
- [x] A selected vehicle shows the approved individual logcard and current-cost
      details.
- [x] No real fleet data, source PDFs or credentials are committed.
- [x] A fresh verified local backup exists before the additive migration is
      applied to the live local database.
- [x] Focused and full tests pass; `git diff --check` passes; independent review
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

- Added configurable legal-owner companies with normalized unique names and
  active/inactive lifecycle.
- Added nullable vehicle identity, exact-capacity, approved logcard and
  current-only cost fields with service and database validation.
- Preserved the existing two-argument vehicle creation and CSV publication
  path; no defaults or estimates are assigned to optional cost fields.
- Added combined company/type/exact-seat Fleet filters, company entry, bounded
  detail update and truthful selected-vehicle detail rendering.
- Grouped the unfiltered Fleet list by registered company and then registration
  number; vehicles without a recorded owner appear last.
- Prefilled and vehicle-scoped detail-form state so an edit preserves recorded
  values and switching vehicles cannot carry values into another record.
- Aligned weight validation with the database `Numeric(10,2)` storage bound.
- Added one additive migration and isolated model, service, migration and page
  tests.

### Files changed

- `advancore/models/{legal_entity,vehicle}.py`, model exports
- `advancore/repositories/{legal_entity,vehicle}.py`, repository exports
- `advancore/services/{legal_entity_service,vehicle_service}.py`
- `advancore/pages/operations.py`
- `alembic/versions/e2f119fleet2_fleet_identity_current_cost.py`
- `tests/test_{legal_entity_service,vehicle_service,operations_page,models,migrations}.py`
- This task completion report

### Database changes

- Additive `legal_entities` table with a unique bounded name and lifecycle.
- Twenty-one nullable columns added to `vehicles`, including a restrictive
  nullable legal-owner foreign key and bounded check constraints.
- The controller created and independently verified fresh local backup
  `advancore-20260827T130051Z-b4b5bb10` before schema work. No migration was
  applied to the live local database during implementation or verification.

### Tests and results

- `python3 -m compileall -q ...`: passed.
- `git diff --check`: passed.
- Initial verification reproduced 13 collection errors because its pytest
  process did not provide the required `DATABASE_URL` setting.
- Final focused pytest with the project virtual environment and an isolated
  in-memory SQLite URL: 49 passed.
- Final full pytest with the same isolated setting after controller review:
  1,242 passed, 2 skipped.
- `alembic heads`: one head, `e2f119fleet2`.
- `python -m compileall` and `git diff --check`: passed.
- Independent review found two detail-update/state risks and one weight-bound
  mismatch; the repairs were reinspected and no bounded issue remained.
- The requested Kimi AgentSwarm repair/review boundary was invoked without
  permission-bypass flags but failed before agent execution because the local
  CLI hit an `EMFILE` watcher error and could not write session storage in the
  managed sandbox.

### Assumptions

- Company-name normalization collapses surrounding/repeated whitespace while
  preserving owner-entered case.
- Weights use non-negative decimal values with two decimal places; current
  monetary amounts use two decimal places and no inferred defaults.
- Empty optional Fleet form values intentionally persist as null.

### Risks / unresolved issues

- Kimi-Swarm was unavailable and Gemini exited unsuccessfully. Codex completed
  implementation; the controller independently reviewed the resulting diff and
  repaired the missing company grouping requirement.
- Singapore compliance meaning and source-document accuracy remain owner/reviewer
  verification points; no compliance rule was inferred.

### Decisions required

- None for TASK-119 implementation review. Applying the migration, importing
  real fleet records, and later merging remain separately gated actions.

### Recommended next step

- Publish the reviewed feature branch for CI/GitGuardian review. Apply the
  additive migration to the local database only after those gates are clean;
  then visually verify the Fleet workflow before importing any real vehicles.
