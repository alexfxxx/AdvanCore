# TASK-117 — Daily Dispatch and Assignment Board

STATUS: COMPLETE

## Objective

Provide one truthful daily view of recorded trips, routes, assignments,
vehicles, and drivers so the operator can see dispatch readiness without
cross-checking several registers.

## Business context

The underlying records exist, but operational coordination currently requires
moving between separate tabs. A read-only daily board can expose unassigned
trips, released assignments, and exact recorded resource conflicts without
inventing schedules or availability.

## In scope

- A deterministic read-only daily dispatch projection service.
- Assigned, released, and unassigned trip classifications.
- Exact detection of a vehicle or driver recorded on multiple active
  assignments for the selected date.
- Lists of active vehicles and drivers not used by an active assignment on the
  selected date.
- A Dispatch tab with date selection, summary, board, and truthful empty state.
- Focused service and presentation tests.

## Out of scope

- Automatic scheduling, optimisation, inferred travel time, assignment writes,
  notifications, migrations, real data, credentials, deployment, or `main`.

## Allowed changed-file scope

- `tasks/TASK-117-daily-dispatch-board.md`
- `advancore/services/dispatch_board_service.py`
- `advancore/pages/operations.py`
- `tests/test_dispatch_board_service.py`
- `tests/test_operations_page.py`

## Database impact

Read-only queries only. No schema or data changes.

## Acceptance criteria

- [ ] Only trips for the selected date appear.
- [ ] Recorded assignments are shown with known route, vehicle, and driver
      labels; missing relations remain explicitly identified.
- [ ] Exact same-day active resource reuse is visibly flagged.
- [ ] Active unallocated resources are derived only from current records.
- [ ] Empty state never creates or suggests sample data.
- [ ] Focused and full tests pass; Bugbot, CI, and GitGuardian are clean.

## Owner decisions

None. The board reports exact database state and makes no scheduling decision.

## Completion report

### Implemented

- Added a deterministic date-filtered dispatch projection.
- Added assigned, released, and unassigned states; exact same-day vehicle and
  driver conflict evidence; and active unallocated resource lists.
- Added a read-only Dispatch tab with truthful summary and empty state.

### Files changed

- `tasks/TASK-117-daily-dispatch-board.md`
- `advancore/services/dispatch_board_service.py`
- `advancore/pages/operations.py`
- `tests/test_dispatch_board_service.py`
- `tests/test_operations_page.py`

### Database changes

None.

### Tests and results

- Focused after independent-review repair: `12 passed in 1.44s`.
- Full repository after independent-review repair: `1216 passed, 2 skipped in
  180.40s`.
- `git diff --check`: passed.

### Assumptions

Only assignment records with status `assigned` reserve a vehicle or driver;
released assignments remain visible but do not reserve resources.

### Risks / unresolved issues

The existing assignment workflow does not automatically prevent same-day
vehicle or driver reuse. This task reports exact conflicts but does not change
that business workflow.

### Decisions required

None.

### Recommended next step

Implement TASK-118 truthful fuel intelligence after integration.
