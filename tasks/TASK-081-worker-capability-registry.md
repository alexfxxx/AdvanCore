# TASK-081 — Worker Capability Registry

STATUS: REVIEW

## Objective

Create one immutable, vendor-neutral source of truth for which AI worker names,
roles, approval states, setup gates, and usage-evidence requirements AdvanCore
recognises.

## Business context

AdvanCore now has Kimi, Kimi-Swarm, Codex, dry-run, and a disabled Gemini
candidate represented in code. Routing and the dashboard must not infer
authority from a display label, installed application, or subscription.

## In scope

- Add a fixed code-owned worker registry with approval states and authorised
  roles separated from proposed/candidate status.
- Represent the existing approved adapters, dry-run simulation, and disabled
  Gemini candidate accurately.
- Provide bounded lookup, listing, eligibility, and consistency validation.
- Keep unknown workers and unverified capabilities absent.
- Add documentation and focused tests.

## Out of scope

- Worker activation, executable discovery, account access, API keys, billing,
  dynamic plugins, database configuration, route selection, or dashboard UI.

## Allowed changed-file scope

- `tasks/TASK-081-worker-capability-registry.md`
- `advancore/agent_runner/worker_registry.py`
- `advancore/agent_runner/__init__.py`
- `docs/architecture/WORKER_CAPABILITY_REGISTRY.md`
- `tests/test_worker_registry.py`

## Database impact

None.

## Acceptance criteria

- [x] Registry names exactly match approved and candidate code-owned names.
- [x] Approval state, launch permission, roles, and setup gates are separate.
- [x] Gemini has no authorised role and cannot be eligible.
- [x] Dry-run cannot be mistaken for a launchable implementation worker.
- [x] Unknown names and roles fail closed.
- [x] Registry is immutable to callers.
- [x] Focused tests and `git diff --check` pass.
- [x] Completion report produced.

## Constraints

- Do not claim provider capabilities that have not been evaluated.
- Do not treat installation or subscription as authority.
- Do not modify or merge to `main`.

## Owner decisions

None for the registry. Gemini activation remains deferred.

## Completion report

### Implemented

- Added frozen profiles and enums for worker identity, approval state, roles,
  setup gates, launchability, and usage-evidence requirements.
- Added deterministic lookup/list/eligibility APIs and import-time consistency
  validation against the code-owned adapter allowlists.
- Kept Gemini ineligible and dry-run simulation-only.

### Files changed

- Task record, immutable worker registry, public exports, architecture note, and
  focused tests.

### Database changes

None.

### Tests and results

- Registry plus Gemini, routing, and fallback regression suite: 36 passed.
- `git diff --check`: passed.

### Assumptions

- Only roles already represented by established worker behavior are registered.

### Risks / unresolved issues

- Registry eligibility is a necessary routing input but does not itself prove
  current executable, authentication, usage, or repository health.

### Decisions required

None.

### Recommended next step

Proceed with TASK-082 deterministic routing using registry eligibility plus
controller-supplied health evidence.
