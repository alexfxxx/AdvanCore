# TASK-084 — Safe Failover and Resumption

STATUS: REVIEW

## Objective

Persist a bounded, credential-free worker-selection checkpoint and permit one
safe next-worker decision only after an eligible provider failure and unchanged
repository fingerprint.

## Business context

If a worker becomes unavailable, AdvanCore must not duplicate work, restart an
already-mutated workspace, or forget why a fallback was selected. The existing
Kimi-to-Codex runtime path remains authoritative; this task adds provider-neutral
checkpoint and resumption primitives for future multi-worker orchestration.

## In scope

- Add strict failover checkpoints with run/task/branch/role, selected and
  attempted workers, failure class, and repository fingerprint only.
- Start from governed selection evidence.
- Permit advancement only for an existing eligible provider failure, unchanged
  fingerprint, unattempted approved worker, and bounded attempt count.
- Save/load checkpoints atomically under a caller-selected controller state
  directory for tests and future orchestration wiring.
- Reject symlinks, path confusion, extra fields, malformed identifiers, unknown
  failures, duplicate workers, and stale fingerprints.
- Add focused tests and documentation.

## Out of scope

- Launching workers, automatic resume after timeout/cancellation, Gemini
  activation, storing prompts/output/credentials, modifying auto-pipeline,
  database persistence, account access, or more than one fallback.

## Allowed changed-file scope

- `tasks/TASK-084-safe-failover-resumption.md`
- `advancore/agent_runner/failover.py`
- `advancore/agent_runner/__init__.py`
- `docs/runbooks/WORKER_ROUTING.md`
- `tests/test_safe_failover.py`

## Database impact

None.

## Acceptance criteria

- [x] Checkpoints contain no prompt, output, environment, credential, or raw
      provider message.
- [x] Unknown failure and changed/ambiguous fingerprint block advancement.
- [x] One worker cannot be attempted twice in a run.
- [x] Only fixed governed selection can choose the next worker.
- [x] Attempt count is bounded to the established primary plus one fallback.
- [x] Save/load is atomic, strict, path-contained, and symlink-safe.
- [x] No worker launch or authority consumption occurs.
- [x] Focused tests and `git diff --check` pass.
- [x] Completion report produced.

## Constraints

- Runtime auto-pipeline integrity checks remain authoritative.
- A timeout/cancellation still needs its separately reviewed recovery action.
- Do not modify or merge to `main`.

## Owner decisions

None for checkpoint primitives. Gemini activation remains deferred.

## Completion report

### Implemented

Credential-free, versioned failover checkpoints with strict validation,
atomic persistence, unchanged-repository enforcement, and one governed fallback.

### Files changed

Only the five files listed in the allowed changed-file scope.

### Database changes

None.

### Tests and results

Focused failover and routing tests passed; `git diff --check` passed.

### Assumptions

The caller supplies a trusted repository fingerprint calculated by the existing
controller integrity boundary.

### Risks / unresolved issues

This primitive intentionally does not auto-resume a cancelled or timed-out
worker and does not launch any worker.

### Decisions required

None for review. Gemini activation remains deferred.

### Recommended next step

Run TASK-085's deterministic multi-worker governance rehearsal without
launching a provider worker.
