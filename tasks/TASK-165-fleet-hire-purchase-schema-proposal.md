# TASK-165 — Fleet Hire-Purchase Schema Proposal

STATUS: COMPLETE

## Objective

Review the minimum additive data contract needed to show approved
hire-purchase information and calculated remaining scheduled payments for a
selected Fleet vehicle.

## Business context

The approved Fleet brief requires finance details in the selected-vehicle view
without adding finance columns to the compact Fleet list. The owner expects to
obtain source information gradually, so every proposed source field is nullable
and missing inputs must remain `Not recorded`.

## Facts

- The approved Fleet brief is
  `tasks/module-briefs/fleet-management.md`.
- Existing vehicle identity and cost fields remain unchanged.
- Remaining scheduled payment count and projected amount are calculated at
  read time and are not stored as independent balances.
- Official lender settlement balance, combined monthly cost and CSV export are
  deferred.

## In scope

- Review five nullable proposed columns on the existing `vehicles` table:
  - `finance_company`: bounded text, maximum 120 characters;
  - `original_loan_amount`: non-negative decimal with two decimal places;
  - `monthly_instalment`: non-negative decimal with two decimal places;
  - `loan_start_date`: calendar date; and
  - `loan_term_months`: positive integer.
- Review non-persisted calculations for remaining scheduled payment count and
  projected remaining scheduled amount.
- Review validation, display and API-contract implications.
- Record the owner's presentation-only requirement for show/hide and draggable
  field order in the subsequent implementation task.

## Out of scope

- Creating or applying a migration.
- Changing models, services, APIs, Streamlit, the decoupled frontend or tests.
- Writing, importing or correcting any real Fleet or finance value.
- Official settlement balance, payment ledger, interest schedule, early or
  irregular payments, refinancing, accounting treatment, combined fixed-cost
  totals, export, credentials, deployment or `main`.

## Proposed database impact

One later additive Alembic migration would add the five nullable columns to
`vehicles`. Existing rows would remain valid and unchanged. Proposed database
checks would require recorded amounts to be non-negative and recorded term
months to be positive. No cross-field completeness check is proposed because
the owner will obtain information gradually; calculations remain unavailable
until all of their required inputs are present.

No migration is authorised by this proposal.

## Allowed changed-file scope

- `tasks/TASK-165-fleet-hire-purchase-schema-proposal.md`
- `tasks/TASK-166-fleet-hire-purchase-implementation.md`
- `tasks/module-briefs/fleet-management.md`

## Proposed calculations

- Scheduled payment number `n`, for `n` from 1 through `loan_term_months`, falls
  `n` calendar months after `loan_start_date`; when a target month lacks the
  starting day, use that month's final calendar day.
- Count scheduled payment dates on or before the calculation date and clamp the
  result between zero and `loan_term_months`.
- Remaining scheduled payments = `loan_term_months` minus elapsed scheduled
  payments.
- Projected remaining scheduled amount = remaining scheduled payments multiplied
  by `monthly_instalment`, rounded to two decimal places.
- If start date or term is missing, remaining payment count is `Not recorded`.
- If monthly instalment is also missing, projected remaining amount is `Not
  recorded`.
- Never label the projected amount as an official settlement balance.

## Proposed application impact

- Extend existing vehicle service validation and selected-vehicle editing.
- Extend the read-only Fleet API response with the five source fields and two
  calculated nullable fields.
- Add finance information only to selected-vehicle details in Streamlit and the
  decoupled Fleet screen.
- Preserve current list columns, filters, imports and all existing vehicle
  identities.

## Acceptance criteria

- [x] Owner approved the exact five nullable source fields.
- [x] Owner approved the calculation behavior and `Not recorded` states.
- [x] No stored field is proposed for either calculated value.
- [x] Existing 27 vehicles remain valid without finance information.
- [x] Implementation is placed in a separate task and approval gate.
- [x] No database, migration, real-data or application file changes occurred.

## Test requirements

If implementation is later approved, focused tests must cover monthly
anniversaries, short months, leap years, future start dates, completed terms,
missing inputs, decimal rounding, negative-value rejection, existing-row
compatibility, API serialization and both selected-vehicle detail surfaces.

## Constraints

- The approved business brief is authoritative.
- `agent_runner` remains the authority boundary.
- A fresh verified local backup is mandatory before applying any later additive
  migration.
- No value may be derived from the 27 real vehicles during implementation
  tests; tests use synthetic records only.

## Module design gate

Classification: BUSINESS_MODULE
Module identifier: fleet_management
Approved brief: tasks/module-briefs/fleet-management.md

## Owner decisions

None

## Completion report

### Implemented

- Recorded owner approval of the five-field nullable schema proposal and the
  read-time payment calculations.
- Added the approved browser-local field-layout requirement to the Fleet brief.
- Prepared TASK-166 as a separate implementation approval boundary.

### Files changed

- `tasks/TASK-165-fleet-hire-purchase-schema-proposal.md`
- `tasks/TASK-166-fleet-hire-purchase-implementation.md`
- `tasks/module-briefs/fleet-management.md`

### Database changes

None. No migration was created or applied.

### Tests and results

- Approved Fleet brief: ready, with 17 confirmed facts, every required section,
  no placeholders, no duplicate sections and no unresolved owner decisions.
- TASK-165 and TASK-166 business-module gates: passed against the approved
  Fleet brief.
- Focused module-design and existing frontend-preference tests: 15 passed.
- `git diff --check`: passed.
- A combined check that also selected `tests/test_api_fleet.py` stopped during
  collection because the existing shared project virtual environment does not
  contain FastAPI. No dependency was installed; no application code changed in
  this proposal, and API testing remains mandatory in TASK-166 implementation.

### Assumptions

Dragging changes only display order. Actual vehicle values remain editable only
through the existing governed Fleet form.

### Risks / unresolved issues

Implementation, migration creation and migration application remain separate
approval boundaries.

### Decisions required

Approve or reject TASK-166 implementation.

### Recommended next step

Review TASK-166, then approve implementation without authorising local migration
application or real finance-data entry.
