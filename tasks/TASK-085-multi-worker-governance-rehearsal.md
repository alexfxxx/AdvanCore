# TASK-085 — Multi-Worker Governance Rehearsal

STATUS: REVIEW

## Objective

Prove the Kimi-first, Codex-fallback, Gemini-candidate policy through a
deterministic offline rehearsal that launches no provider worker.

## Business context

Before adding another provider or wiring automatic failover into live task
execution, AdvanCore needs repeatable proof that selection and resumption stop
at every authority, evidence, and integrity boundary.

## In scope

- Rehearse healthy Kimi, paused Kimi, Codex fallback, and unavailable evidence.
- Rehearse one eligible failover, repository drift, unknown failure, and route
  exhaustion.
- Rehearse Gemini's disabled owner-action boundary.
- Produce a small credential-free report and focused tests.

## Out of scope

Provider launches, account access, Gemini authentication or activation, API
keys, billing, live database changes, deployment, and merging to `main`.

## Allowed changed-file scope

- `tasks/TASK-085-multi-worker-governance-rehearsal.md`
- `advancore/agent_runner/worker_rehearsal.py`
- `advancore/agent_runner/__init__.py`
- `docs/validation/MULTI_WORKER_GOVERNANCE_REHEARSAL.md`
- `tests/test_multi_worker_rehearsal.py`

## Database impact

None.

## Acceptance criteria

- [x] Kimi-first and Codex-fallback policy is exercised.
- [x] Gemini cannot be selected or launched.
- [x] Missing evidence, unknown failure, and repository drift fail closed.
- [x] Failover stops after one fallback.
- [x] No worker, account, database, or authority is used.
- [x] Report content is bounded and credential-free.
- [x] Focused tests and `git diff --check` pass.
- [x] Completion report produced.

## Constraints

This rehearsal does not prove external provider health or authorize candidate
activation. Existing controller and `agent_runner` boundaries remain final.

## Owner decisions

None for offline rehearsal. Gemini activation remains a future owner decision.

## Completion report

### Implemented

Nine deterministic scenarios covering routing priority, evidence failure,
single-hop failover, repository integrity, route exhaustion, and candidate
isolation.

### Files changed

Only the five files listed in the allowed changed-file scope.

### Database changes

None.

### Tests and results

Focused rehearsal, failover, routing, registry, and Gemini boundary tests pass;
`git diff --check` passes.

### Assumptions

External worker availability remains controller-supplied evidence.

### Risks / unresolved issues

The rehearsal intentionally does not launch providers, so it cannot establish
their current service or account status.

### Decisions required

None.

### Recommended next step

Independently review TASK-079 through TASK-085, then publish the reviewed
feature branch without merging to `main`.
