# TASK-166 — Fleet Hire-Purchase and Configurable Detail Display

STATUS: COMPLETE

## Objective

Implement the approved five-field Fleet hire-purchase extension, safe read-time
remaining-payment calculations, and browser-local show/hide/reorder controls
for selected-vehicle detail fields without applying the migration locally.

## Business context

The owner needs finance visibility for vehicles still under hire purchase and
wants to choose which approved details are visible and how they are arranged.
Information will be obtained gradually, so partial source data must remain
truthful and calculations must remain unavailable until their required inputs
exist.

## Facts

- `tasks/module-briefs/fleet-management.md` is owner-approved and passes the
  module-design gate.
- TASK-165 approved five nullable source fields and two derived display values.
- The existing Fleet screen is the governed vehicle edit surface.
- The decoupled local console already uses validated browser `localStorage` for
  presentation preferences and exposes Fleet through a read-only API.
- Dragging fields changes presentation only; it cannot mutate PostgreSQL or a
  vehicle value.

## In scope

- Add nullable `finance_company`, `original_loan_amount`,
  `monthly_instalment`, `loan_start_date` and `loan_term_months` fields to the
  vehicle model through one additive Alembic migration.
- Do not apply that migration to the local operational database in this task.
- Validate bounded finance-company text, non-negative two-decimal amounts,
  positive term months and nullable partial records.
- Add a deterministic service calculation for remaining scheduled payment count
  and projected remaining scheduled amount using the approved monthly-date
  rules.
- Extend the existing Streamlit selected-vehicle form and detail display with
  the five source fields and two derived values.
- Extend the read-only Fleet API contract with the five source fields and two
  derived nullable values.
- Extend the decoupled selected-vehicle detail presentation with a code-owned
  field catalog, show/hide controls, drag ordering, keyboard-accessible move
  controls, safe defaults and reset.
- Store only validated field identifiers, visibility and order in a new
  versioned browser-local preference key.
- Preserve current company/type/capacity filters, compact Fleet list and all
  existing records.
- Add focused model, migration, service, Streamlit, API, frontend-contract and
  calculation tests using synthetic records.

## Out of scope

- Applying the migration, modifying the live database or entering/importing
  real finance information.
- Making the decoupled API a vehicle-write surface.
- Dragging a field to change its value or database identity.
- Arbitrary user-created schema fields, arbitrary HTML/CSS/JavaScript, server-
  stored layout preferences or cross-device synchronization.
- Official lender settlement balance, payment ledger, interest or amortization
  schedule, early/irregular payments, refinancing or finance reconciliation.
- Finance columns in the compact Fleet list, combined fixed-cost summary, CSV
  export, fuel, workshop charging, maintenance, drivers or dispatch.
- Authentication, external accounts, credentials, billing, deployment or
  `main`.

## Allowed changed-file scope

- `tasks/TASK-166-fleet-hire-purchase-implementation.md`
- `advancore/models/vehicle.py`
- `advancore/services/vehicle_service.py`
- `advancore/pages/operations.py`
- `advancore/api/schemas.py`
- `advancore/api/dependencies.py`
- `frontend/index.html`
- `frontend/app.js`
- `frontend/styles.css`
- `alembic/versions/*_fleet_hire_purchase.py`
- `tests/test_models.py`
- `tests/test_migrations.py`
- `tests/test_vehicle_service.py`
- `tests/test_operations_page.py`
- `tests/test_api_fleet.py`
- `tests/api_operations_helpers.py`
- `tests/test_frontend_preferences_contract.py`
- `tests/test_frontend_fleet_contract.py`

## Database impact

One additive migration file may be created with five nullable columns and
bounded checks. It must not be applied in this task. Existing 27 vehicle rows
must remain valid at the pre-migration and post-migration schema shapes.

## Display preference contract

- Registration number and status stay pinned as vehicle identity.
- Only code-owned approved detail-field identifiers can be displayed or moved.
- Desktop supports drag ordering; touch and keyboard users receive equivalent
  move controls.
- Hiding a field affects display only and never clears its saved value.
- Invalid, duplicated, obsolete or unknown stored identifiers are ignored and
  replaced with safe defaults.
- Reset restores the approved order and visibility.
- Preferences remain on the current browser/device and are never sent to the
  API.

## Acceptance criteria

- [x] All five source fields are nullable and existing vehicles remain valid.
- [x] Derived values are calculated at read time and are never persisted.
- [x] Short months, leap years, future starts, completed terms and missing
      inputs follow the approved calculation rules.
- [x] Negative amounts and non-positive terms are rejected consistently by
      service and database constraints.
- [x] Streamlit can edit and truthfully display approved finance information.
- [x] The read-only API returns source and derived values without adding a write
      route.
- [x] The decoupled console can show, hide and reorder approved detail fields
      without changing operational data.
- [x] Display preferences persist after refresh, reject unsafe stored content,
      support keyboard/touch alternatives and reset safely.
- [x] Current Fleet filters, compact list and existing imports remain compatible.
- [x] Focused and full isolated tests pass; `git diff --check` passes.
- [x] Independent Bugbot review has no unresolved findings.
- [x] No migration is applied and no real finance data is entered.

## Test requirements

- Unit-test payment dates across 28/29/30/31-day months and leap years.
- Test dates before the first payment, on a due date, after term completion and
  with each required input missing.
- Test decimal rounding, validation bounds and existing two-field vehicle
  creation compatibility.
- Inspect additive migration lineage and downgrade behavior using an isolated
  database only.
- Test Streamlit field rendering/update and API serialization with synthetic
  values.
- Test field-catalog allowlisting, drag/move order, visibility, persistence,
  invalid preference recovery and reset without network calls.
- Run focused tests, full dependency-independent regression, compilation and
  `git diff --check`.

## Constraints

- `agent_runner` remains the authority boundary; a worker cannot approve its
  own implementation.
- Kimi Swarm is reserved for eligible large parallel work. Worker fallback must
  follow controller policy and preserve scope.
- Do not expose credentials or inherit unrelated controller environment values.
- Do not store or log real finance documents or values during tests.
- GitHub remains the source of truth. Publication may target only the feature
  branch and later `projects-lifecycle-recovery`, never `main`.
- A fresh verified backup and separate owner approval are mandatory before any
  later local migration application.

## Module design gate

Classification: BUSINESS_MODULE
Module identifier: fleet_management
Approved brief: tasks/module-briefs/fleet-management.md

## Owner decisions

None. The owner approved implementation on 30 August 2026 without authorising
migration application or real finance-data entry.

## Completion report

### Implemented

- Added the five approved nullable hire-purchase source fields and matching
  service/database validation.
- Added deterministic read-time remaining-payment count and projected scheduled
  amount calculations, including short-month and leap-year behavior.
- Extended the governed Streamlit edit/detail surface and read-only Fleet API.
- Added an allow-listed browser-local Fleet field catalog with show/hide,
  desktop drag ordering, touch/keyboard move controls and safe reset.
- Created additive migration revision `f3e166fleet3` without applying it.
- Repaired Bugbot's downward/final-position drag finding and added a behavioral
  Node-backed contract test.

### Files changed

- `advancore/models/vehicle.py`
- `advancore/services/vehicle_service.py`
- `advancore/pages/operations.py`
- `advancore/api/schemas.py`
- `advancore/api/dependencies.py`
- `frontend/index.html`
- `frontend/app.js`
- `frontend/styles.css`
- `alembic/versions/f3e166fleet3_fleet_hire_purchase.py`
- `tests/test_models.py`
- `tests/test_migrations.py`
- `tests/test_vehicle_service.py`
- `tests/test_operations_page.py`
- `tests/test_api_fleet.py`
- `tests/api_operations_helpers.py`
- `tests/test_frontend_fleet_contract.py`
- This task file and its TASK-164/TASK-165 design records.

### Database changes

- One additive migration file was created with five nullable columns and three
  bounded check constraints.
- The migration was not applied. No local PostgreSQL connection, real vehicle
  update or finance-data entry occurred.

### Tests and results

- Initial focused model/service/migration/Streamlit/frontend checks: 64 passed.
- Post-Bugbot focused checks, including behavioral drag ordering: 65 passed.
- Broad dependency-independent isolated regression: 1,543 passed, 2 skipped.
- Six isolated FastAPI files: 32 passed with one third-party Starlette
  deprecation warning.
- Python compilation, JavaScript syntax, `git diff --check` and Alembic single
  head `f3e166fleet3`: passed.
- Initial Bugbot review found one P2 drag-direction/final-position defect; the
  approved bounded repair was completed and the Bugbot rerun returned clean.

### Assumptions

- Browser field arrangement applies to the decoupled local console. Streamlit
  remains the governed source-value edit surface.
- Browser preferences are intentionally device-local and do not synchronize.

### Risks / unresolved issues

- The feature must not be activated against the current local PostgreSQL schema
  until a fresh verified backup and separate migration-application approval.
- No real finance values have been verified or entered.

### Decisions required

- Commit and publish this reviewed feature branch, or request further review.
- Separately approve a fresh backup and local migration application only after
  publication gates are clean.

### Recommended next step

Commit TASK-164 through TASK-166 on this feature branch, push it, run GitHub CI
and GitGuardian, and prepare a PR into `projects-lifecycle-recovery`, not
`main`. Do not apply the migration yet.
