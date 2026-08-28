# TASK-134 — Decoupled Fleet Screen

STATUS: COMPLETE

## Objective
Show the real Fleet register in the decoupled frontend using the TASK-133 read-only API.

## In scope
- Company, vehicle-type, and exact-seating filters.
- Fleet list and individual detail display using existing fields only.
- Truthful empty, unavailable, and null-value states.

## Out of scope
- Editing, importing, fabricated values, new fields, or database writes.

## Database impact
None.

## Allowed changed-file scope
- `frontend/**`
- `tests/test_frontend_fleet_contract.py`
- This task file

## Acceptance criteria
- [x] Existing vehicles render without manual re-entry.
- [x] Filters match the approved Fleet rules.
- [x] Text wraps and desktop/mobile layouts pass.

## Owner decisions
None.

## Completion report
The decoupled console now renders the existing Fleet register with company,
vehicle-type and exact-seat filters plus truthful null states. Visual checks
against the local database showed all 27 imported vehicles; filtering Bus plus
43 seats returned three records. Desktop and 390-pixel mobile checks passed on
28 August 2026.
