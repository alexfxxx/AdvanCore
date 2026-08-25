# TASK-082 — Governed Worker Selection

STATUS: REVIEW

## Objective

Select the first eligible approved worker from fixed role-specific preferences
using explicit controller health/usage evidence, without launching a process or
granting new authority.

## Business context

Multiple worker identities are now represented in one registry. AdvanCore needs
a deterministic decision layer that prefers Kimi where approved, uses Codex
when the primary is unavailable, and never treats a candidate or stale status
as available.

## In scope

- Add bounded availability states and controller evidence records.
- Add code-owned preferences for implementation, planning, review, and fallback.
- Select only registry-approved, launchable workers with the requested role and
  explicit AVAILABLE evidence.
- Record bounded considered/selected reason codes for audit and rehearsal.
- Preserve the existing launch, usage, authority, integrity, and one-hop
  fallback gates after selection.
- Add focused tests and routing documentation.

## Out of scope

- Worker launch, executable/account probing, Gemini activation, credentials,
  dynamic caller-controlled order, database persistence, dashboard UI, or
  changes to the production unattended route.

## Allowed changed-file scope

- `tasks/TASK-082-governed-worker-selection.md`
- `advancore/agent_runner/worker_routing.py`
- `advancore/agent_runner/__init__.py`
- `docs/runbooks/WORKER_ROUTING.md`
- `tests/test_governed_worker_selection.py`

## Database impact

None.

## Acceptance criteria

- [x] Role preferences are fixed in code and cannot be supplied by a caller.
- [x] Kimi-Swarm is preferred for implementation when explicitly available.
- [x] Codex is selected when Kimi-Swarm is paused, stale, or unavailable.
- [x] Missing evidence is unavailable, never assumed healthy.
- [x] Gemini remains ineligible even if evidence says available.
- [x] Unknown workers/roles and duplicate evidence fail closed.
- [x] Selection performs no launch or authority consumption.
- [x] Focused tests and `git diff --check` pass.
- [x] Completion report produced.

## Constraints

- Selection evidence is controller-owned input; workers cannot self-report
  approval or availability.
- Existing preflight and launch checks must still run after selection.
- Do not modify or merge to `main`.

## Owner decisions

None. Gemini activation remains deferred.

## Completion report

### Implemented

- Added bounded controller availability states and immutable evidence records.
- Added fixed role-specific preferences and deterministic selection evidence.
- Enforced registry role/approval/launchability before availability can select
  a worker.
- Kept selection pure: no adapter construction, process launch, or authority
  consumption.

### Files changed

- Task record, worker-routing selection layer, public exports, runbook, and
  focused tests.

### Database changes

None.

### Tests and results

- Selection, registry, established routing, and fallback tests: 42 passed.
- `git diff --check`: passed.

### Assumptions

- Controller health/usage collection supplies explicit availability evidence;
  selection never manufactures it.

### Risks / unresolved issues

- This task deliberately does not replace the proven production launch route;
  it provides the deterministic decision layer used by later health/failover
  work.

### Decisions required

None.

### Recommended next step

Proceed with TASK-083 provider-neutral usage and health summaries plus a
truthful dashboard view.
