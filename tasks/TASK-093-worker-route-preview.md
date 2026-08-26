# TASK-093 — Governed Worker Route Preview

STATUS: REVIEW

## Objective

Provide a read-only preview of the worker that current explicit evidence would
select from the permanent code-owned route.

## Business context

The owner needs to understand whether Kimi is presently selectable or whether
the controller will require a launch-time fallback check, without starting a
worker or consuming authority.

## In scope

- Expose immutable role preference tuples from the existing selector.
- Build evidence only for those fixed preferences.
- Return selected or blocked with bounded reasons.
- Record explicitly that preview launches zero workers and consumes no
  authority.

## Out of scope

Worker probes or launches, automatic fallback, Gemini routing/authentication,
credentials, database changes, deployment, or `main`.

## Allowed changed-file scope

- `tasks/TASK-093-worker-route-preview.md`
- `advancore/agent_runner/worker_routing.py`
- `advancore/agent_runner/__init__.py`
- `advancore/services/worker_route_preview_service.py`
- `tests/test_worker_route_preview_service.py`
- `tests/test_governed_worker_selection.py`

## Database impact

None.

## Acceptance criteria

- [x] Preview uses the selector's code-owned preference order.
- [x] Missing evidence produces blocked, not guessed availability.
- [x] Gemini is absent from every production preference.
- [x] Preview starts no process and consumes no authority.
- [x] Focused tests and `git diff --check` pass.
- [x] Completion report produced.

## Constraints

Actual adapters still perform their established launch-time gates.

## Owner decisions

None.

## Completion report

### Implemented

Immutable preference access and a bounded read-only route preview service.

### Files changed

Only the task, routing API/export, preview service, and focused tests.

### Database changes

None.

### Tests and results

Focused preview, selector, registry, and evidence tests pass; `git diff --check`
passes.

### Assumptions

Pre-launch Codex status remains unproven until its fixed adapter launch check.

### Risks / unresolved issues

A blocked preview may still permit Codex after an actual launch-time check; the
UI must explain this without claiming current availability.

### Decisions required

None.

### Recommended next step

Render routing and governance rehearsal status in AI Center in TASK-094.
