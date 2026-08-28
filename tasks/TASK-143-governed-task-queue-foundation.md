# TASK-143 — Governed Task Queue Foundation

STATUS: COMPLETE

## Objective

Create a controller-owned queue for already approved governed tasks so future
unattended work can be sequenced without accepting arbitrary commands or
bypassing `agent_runner`.

## Business context

The owner wants exception-based operation across several approved tasks. A queue
must describe work waiting for the controller, not become a second executor or
authority boundary.

## In scope

- Create `advancore/agent_runner/task_queue.py` containing a bounded
  `TaskQueueStatus` string enum, immutable JSON-safe queue record type and a
  `GovernedTaskQueue` service. Implement explicit `enqueue`, `claim_next`,
  `complete` and `block` methods; do not merely propose the design.
- Create `tests/test_task_queue.py` with deterministic coverage for FIFO order,
  duplicate rejection, invalid identifiers/paths/workers/transitions, stale
  claims, corrupt or oversized state, permissions and atomic replacement.
- Create `docs/runbooks/GOVERNED_TASK_QUEUE.md` explaining that the queue cannot
  launch, approve, publish or merge work.
- Add a local queue service with bounded `QUEUED`, `RUNNING`, `COMPLETED` and
  `BLOCKED` states.
- Accept only canonical TASK identifiers, repository-relative governed task-file
  paths, registered worker names and safe timestamps/status metadata.
- Store the queue outside worker repositories with owner-only permissions,
  bounded records, atomic writes and deterministic FIFO ordering.
- Require explicit controller methods for enqueue, claim, complete and block;
  reject invalid transitions, duplicates, stale claims and malformed state.
- Store no prompt, task body, command, credential, worker output, business data
  or publication authority.
- Add deterministic tests and a short operations runbook.

## Out of scope

- Launching workers, choosing fallbacks, retries, approvals, Git operations,
  publication, merges or deployment.
- Dashboard/UI work, PostgreSQL, Alembic, migrations or real data.
- Arbitrary paths, commands, URLs, account identifiers or environment values.

## Allowed changed-file scope

- `tasks/TASK-143-governed-task-queue-foundation.md`
- `advancore/agent_runner/task_queue.py`
- `tests/test_task_queue.py`
- `docs/runbooks/GOVERNED_TASK_QUEUE.md`

## Database impact

None.

## Acceptance criteria

- [x] Approved tasks can be queued and claimed in deterministic FIFO order.
- [x] State transitions are explicit, valid and fail closed.
- [x] Duplicate, malformed, stale or unsafe records cannot launch or authorize
      anything.
- [x] Storage is bounded, atomic, owner-only and outside worker repositories.
- [x] Focused tests, full tests and `git diff --check` pass.

## Owner decisions

Approved for unattended implementation on 28 August 2026. Gemini is the
assigned implementation worker; Codex remains controller and final fallback.

## Completion report

### Implemented

- Added a bounded, owner-only queue with deterministic FIFO ordering and
  explicit `QUEUED`, `RUNNING`, `COMPLETED` and `BLOCKED` transitions.
- Added an owner-only lock, atomic replacement, strict record validation and a
  two-hour stale-claim block that never silently retries work.
- Required a real, direct `READY` or `REWORK` governed task file both when a
  record is enqueued and immediately before it is claimed.
- Preserved actual enqueue order for equal timestamps and rejected backward
  transition times before they can be persisted.
- Bound task, lock and state operations to no-follow directory descriptors,
  rejected hard-linked locks, and enforced one active claim in loaded state.
- Kept state paths lexical until descriptor binding, opened task leaves
  non-blocking, and normalized deeply nested JSON failures.
- Documented that the queue has no worker-launch, approval, publication, merge,
  database or deployment authority.

### Worker routing evidence

- Gemini was launched three times, including twice with exact file and method
  context. Each invocation exited successfully but produced no repository
  changes; the final attempt therefore failed the contract tests.
- Codex completed the bounded implementation as the approved final fallback.

### Database changes

None.

### Verification

- Focused tests: 14 passed.
- Full post-rebase suite: 1,309 passed, 2 skipped.
- `git diff --check`: passed.

### Decisions required

None.
