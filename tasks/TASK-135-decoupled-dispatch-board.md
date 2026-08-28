# TASK-135 — Decoupled Daily Dispatch Board

STATUS: COMPLETE

## Objective
Show the existing truthful Daily Dispatch view in the decoupled frontend.

## In scope
- Read existing trips, routes, assignments, vehicles, and drivers through rollback-only services.
- Display recorded readiness, conflicts, and available resources from the existing dispatch-board service.

## Out of scope
- Assignment writes, optimisation, invented schedules, notifications, new fields, or migrations.

## Database impact
None.

## Allowed changed-file scope
- `advancore/api/**`
- `frontend/**`
- `tests/test_api_dispatch.py`
- `tests/test_frontend_dispatch_contract.py`
- This task file

## Acceptance criteria
- [x] Board derives only from existing records and service rules.
- [x] Missing links remain visibly missing, never guessed.
- [x] Tests and mobile/desktop checks pass.

## Owner decisions
None.

## Completion report
Added a dated read-only dispatch endpoint and console board backed by the
existing dispatch-board service. It displays recorded trips, assignments,
conflicts and available resources without an assignment write path. Tests and
responsive visual checks passed on 28 August 2026.
