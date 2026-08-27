# TASK-134 — Decoupled Fleet Screen

STATUS: READY

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
- [ ] Existing vehicles render without manual re-entry.
- [ ] Filters match the approved Fleet rules.
- [ ] Text wraps and desktop/mobile layouts pass.

## Owner decisions
None.

## Completion report
Pending.
