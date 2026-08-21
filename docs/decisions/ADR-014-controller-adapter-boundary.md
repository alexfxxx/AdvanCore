# ADR-014 — Controller Adapter Boundary

## Status

Approved and implemented as part of TASK-014.

## Context

TASK-005 introduced a replaceable `WorkerAdapter` boundary for worker execution.
TASK-010 added the deterministic controller review bundle, TASK-011 added the
deterministic controller decision record, TASK-012 added the decision-to-lifecycle
bridge, and TASK-013 added the controller handoff queue that links a review bundle
to an outstanding decision.

The remaining gap was a symmetric replaceable boundary for the controller side:
something that consumes a validated handoff request and returns a bounded result
representing whether a controller decision has been returned. Without that
boundary, any future integration with an independent controller would have to be
wired directly into CLI/orchestration code, increasing coupling and risking
governance drift.

## Decision

Introduce a small `controller_adapter` module and a `controller-adapter` CLI
subcommand that loads a handoff request, invokes exactly one selected adapter,
validates the returned result, and reconciles any reported decision through the
existing TASK-013 handoff logic.

Key choices:

1. **Transport/orchestration boundary, not authority source.** A controller
   adapter consumes a validated handoff request and returns a bounded result. It
   does not make a worker into a controller, treat a handoff request as approval,
   fabricate an `APPROVE` decision, bypass TASK-011 decision validation, bypass
   TASK-012 lifecycle authority, or mutate task/Git/database state.

2. **Small explicit result state model.**
   - `PENDING` — the handoff request is valid but no controller decision has been
     returned.
   - `DECISION_RECEIVED` — a valid controller decision has been returned or was
     already reconciled to the request.
   - `BLOCKED` — adapter execution failed or returned evidence is missing,
     malformed, inconsistent, unauthorized, or unsafe.

3. **Bounded safe input.** The adapter receives only the validated handoff
   request, its path, the repository root, and an optional Git snapshot. It never
   receives the full task body, worker transcripts, credentials, environment
   dumps, or arbitrary repository contents.

4. **Built-in `manual` adapter.** The default adapter is local, read-only, and
   performs no network or subprocess execution. It validates the handoff request,
   exposes bounded handoff metadata, and returns `PENDING` until a separately
   valid controller decision exists. It never infers a decision from the review
   bundle recommendation.

5. **Reconciliation delegation.** If an adapter returns `DECISION_RECEIVED` with a
   decision path, the orchestrator resolves the path and reconciles the decision
   through the existing TASK-013 `reconcile_controller_handoff()` function. No
   reconciliation rules are duplicated in the adapter layer.

6. **No lifecycle bridge invocation.** Adapter dispatch does not call the TASK-012
   `apply_controller_decision()` bridge and does not mutate task lifecycle state.

7. **No Git publication.** Adapter dispatch/status does not stage, commit, push,
   merge, deploy, switch branches, access secrets, or run external subprocesses.

8. **Read-only inspection.** `controller-adapter status` loads the handoff and
   reports its current state as an adapter result. It does not reconcile
   decisions, write artifacts, or mutate task/Git state.

9. **Audit extension.** A new `mode: "controller_adapter"` audit payload records
   every dispatch attempt with safe metadata: task identity, adapter name, result
   state, handoff and decision references, reconciliation flag, branch, and HEAD.
   Full content, transcripts, credentials, and business data are excluded.

## Consequences

- The local runner now has a replaceable controller-adapter boundary analogous to
  the existing worker-adapter boundary.
- A future task can add a remote controller adapter by implementing the
  `ControllerAdapter` interface and registering it, without redesigning handoff,
  decision, or lifecycle semantics.
- Workers cannot impersonate controllers through the adapter boundary; returned
  decisions are validated and reconciled through TASK-013.
- Missing, malformed, inconsistent, unauthorized, or unsafe adapter results fail
  closed as `BLOCKED`.
- Adapter audit records provide local traceability independent of the handoff,
  decision-record, and lifecycle-bridge audit trails.

## Alternatives considered

- **Have the adapter directly write controller decision records.** Rejected: the
  adapter is a transport boundary, not an authority source. Decision records must
  be created by an allowed controller/owner actor through the existing TASK-011
  path.
- **Have the adapter automatically apply lifecycle transitions.** Rejected: the
  TASK-012 bridge remains the only decision-to-lifecycle bridge; adapter dispatch
  must not mutate task state.
- **Allow the adapter to receive the full review bundle contents or task body.**
  Rejected: the input is limited to bounded handoff metadata and references to
  preserve the safe-field policy.
- **Implement a remote HTTP adapter in this task.** Rejected: remote/network
  transport is explicitly out of scope for TASK-014.

## Compliance / risks

- No production data, secrets, or production databases are accessed.
- No schema changes or migrations were introduced.
- No Git commit/push/merge/branch-switch/deployment behavior was added.
- Adapter artifacts and audit records exclude full task bodies, worker
  transcripts, credentials, environment dumps, and business/customer data.
- A worker cannot use the adapter boundary to self-approve; worker-authored
  decisions are rejected at reconciliation.
