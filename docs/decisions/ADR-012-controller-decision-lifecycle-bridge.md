# ADR-012 — Controller Decision Lifecycle Bridge

## Status

Approved and implemented as part of TASK-012.

## Context

TASK-009 introduced an authority-aware task lifecycle state machine and
`transition_task()` helper. TASK-010 added a deterministic review bundle. TASK-011
added a deterministic controller decision record that captures an independent
controller/reviewer decision against a specific review bundle.

The decision record is intentionally passive: recording `APPROVE`, `REWORK`, or
`BLOCKED` does not perform any automatic action. The remaining gap was a
controlled, auditable bridge from that decision record back into the lifecycle
state machine, without giving workers approval authority and without adding
commit/push/merge/deployment capabilities.

## Decision

Introduce a small `decision_lifecycle_bridge` module and a
`controller-decision apply` CLI subcommand that connects a validated decision
record to the existing lifecycle transition helper.

Key choices:

1. **Fail-closed, bounded bridge.** The bridge module validates every linkage
   step before requesting a lifecycle transition. It returns a structured result
   with clear messages rather than raising for expected validation failures.

2. **Preview by default, explicit `--apply`.** The CLI default is read-only
   preview. The task file is mutated only when `--apply` is supplied and every
   validation step passes.

3. **Decision mapping.**
   - `APPROVE` → requested target `APPROVED`
   - `REWORK` → requested target `REWORK`
   - `BLOCKED` → requested target `BLOCKED`

4. **Reuse TASK-009 authority.** The bridge calls `transition_task()` with the
   decision actor and mapped target status. It does not implement a parallel
   transition-authority model. This means an `APPROVE` decision against a task
   in `READY`, `IN_PROGRESS`, or `REWORK` is denied, because the existing state
   machine does not permit a direct transition to `APPROVED` from those states.

5. **Linkage validation.** The bridge checks:
   - decision record exists and parses,
   - decision value is known,
   - actor role is `controller` or `owner` (never `worker`),
   - linked review bundle exists and parses,
   - decision, bundle, and task task IDs agree,
   - decision, bundle, and task filenames agree,
   - current branch equals bundle branch,
   - linked task file exists and identity matches,
   - lifecycle transition is valid for current status and actor.

6. **HEAD evidence surfaced, not enforced as policy.** The bridge reports
   current HEAD, bundle pre HEAD, and bundle post HEAD so that freshness is
   visible and testable. It does not require current HEAD to equal bundle HEAD,
   because doing so would block valid post-review human commits without an
   approved policy.

7. **Only `STATUS:` line changes.** When `--apply` succeeds, only the linked
   task file's `STATUS:` line is rewritten, through the existing
   `transition_task()` helper.

8. **No Git publication.** The bridge does not stage, commit, push, merge,
   deploy, or switch branches.

9. **Audit extension.** A new `mode: "bridge"` audit payload records every
   preview/apply attempt with safe metadata: task identity, decision, target
   status, transition allowed/applied, branch, HEAD, decision path, bundle path,
   and bundle HEADs. Full task bodies, worker transcripts, credentials, notes,
   and business/customer data are excluded.

## Consequences

- Controllers and owners can now preview or explicitly apply a recorded decision
  to a task lifecycle while the lifecycle state machine remains the single
  authority.
- The bridge strengthens the control-plane return path without automating
  commit/push/merge/deployment.
- Workers remain unable to self-approve through decision records or the bridge.
- Missing, malformed, inconsistent, or stale linkage evidence fails closed.
- The bridge audit record provides local traceability for decision-to-lifecycle
  attempts independent of the underlying lifecycle audit record.

## Alternatives considered

- **Automatically transition task status when a decision record is created.**
  Rejected: the decision record must remain a passive artifact; the bridge
  requires a separate explicit `apply` invocation.
- **Implement a parallel transition-authority model inside the bridge.**
  Rejected: the existing TASK-009 lifecycle module already provides the correct
  authority matrix and should remain the single source of truth.
- **Enforce current HEAD equals bundle pre/post HEAD.** Rejected: this would
  block valid post-review human commits and is an owner-level policy decision,
  not something the bridge should silently invent.
- **Apply the decision record by default.** Rejected: preview-first behavior
  matches the existing `transition` command and prevents accidental mutations.

## Compliance / risks

- No production data, secrets, or production databases are accessed.
- No schema changes or migrations were introduced.
- No Git commit/push/merge/branch-switch/deployment behavior was added.
- Bridge audit records exclude task bodies, worker transcripts, credentials,
  environment dumps, arbitrary notes, and business/customer data.
- A worker cannot use the bridge to self-approve; worker actors are rejected.
