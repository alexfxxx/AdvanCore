# ADR-005 — Task Lifecycle Control Plane

## Status

Approved and implemented as part of TASK-009.

## Context

TASK-005 through TASK-008 established a fail-closed local agent runner, real
Kimi execution, post-worker Git verification, explicit approval gating, and
local audit records. Task files in `tasks/` already had informal status values
(DRAFT, READY, IN_PROGRESS, REVIEW, REWORK, APPROVED, BLOCKED), but lifecycle
changes were edited by hand with no validation, no authority model, and no
audit trail.

This created a control gap: a worker or controller could silently move a task
between states, a worker could approve its own work, and an accidental edit
could corrupt task metadata. TASK-009 was chartered to make lifecycle changes
explicit, validated, authority-aware, and auditable without granting any new
Git commit/push/merge authority.

## Decision

Introduce a small task lifecycle control plane inside the local agent runner.

Key choices:

1. **Explicit state model.** `TaskStatus` enumerates the seven repository
   statuses. The state machine is encoded in code, not convention.

2. **Explicit authority model.** `ActorRole` distinguishes `worker`,
   `controller` (controller/reviewer), and `owner`. A pure
   `is_transition_allowed()` function validates both the transition and the
   actor. A worker may not approve its own work.

3. **Allowed transitions.**
   - DRAFT → READY (controller, owner)
   - READY → IN_PROGRESS (worker, owner)
   - IN_PROGRESS → REVIEW (worker, owner)
   - REVIEW → APPROVED (controller, owner)
   - REVIEW → REWORK (controller, owner)
   - REWORK → IN_PROGRESS (worker, owner)
   - any non-final working state → BLOCKED (controller, owner)
   - BLOCKED → READY / REWORK (controller, owner)

4. **Dry-run by default.** The `transition` CLI subcommand previews the change
   unless `--apply` is passed. This mirrors the runner's existing dry-run-first
   policy.

5. **Only the `STATUS:` line is mutated.** `transition_task()` validates the
   file, rejects missing or duplicate `STATUS:` lines, and rewrites exactly one
   line. The task body is preserved.

6. **Audit every attempt.** Every transition attempt appends a JSON Lines
   record to the existing `.agent_runner/audit/runner.jsonl` with safe metadata
   only: task ID/filename, actor role, previous status, requested status,
   allowed/denied result, applied/preview mode, branch, and HEAD SHA. No task
   body content is stored.

7. **No Git mutations.** The lifecycle helper does not commit, push, merge,
   branch-switch, or otherwise change repository state.

## Consequences

- Task status changes are now fail-closed and authority-aware.
- Workers cannot self-approve; controller/reviewer approval remains a distinct
  human-controlled gate.
- Every lifecycle attempt leaves a durable trace for compliance and debugging.
- The default preview behaviour prevents accidental task-file edits.
- The implementation is local and dependency-free, consistent with the existing
  runner architecture.

## Alternatives considered

- **Allow the worker to transition REVIEW → APPROVED after passing tests.**
  Rejected: passing tests do not equal review acceptance; self-approval is
  explicitly out of scope.
- **Store lifecycle state in a database instead of task files.** Rejected:
  GitHub task files are the approved source of truth for scope and status;
  introducing a separate state store would create synchronization risk before
  the need is proven.
- **Let task file content supply executable commands or hooks on transition.**
  Rejected: task files must remain passive documents, not executable control
  surfaces.
- **Batch transitions across multiple task files.** Rejected: one task at a
  time keeps changes reviewable and failures isolated.

## Compliance / risks

- No production data, secrets, or production databases are accessed.
- No schema changes or migrations were introduced.
- No Git commit/push/merge/branch-switch behavior was added.
- Task body content is excluded from audit records.
- The lifecycle helper fails closed on malformed or ambiguous task files.
