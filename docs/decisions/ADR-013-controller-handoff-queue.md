# ADR-013 — Controller Handoff Queue

## Status

Approved and implemented as part of TASK-013.

## Context

TASK-010 introduced the deterministic controller review bundle and TASK-011
introduced the deterministic controller decision record. TASK-012 added a
fail-closed bridge from a validated decision record back into the existing task
lifecycle state machine.

The remaining gap was explicit local orchestration: the runner had no
machine-readable artifact representing “this review bundle is waiting for an
independent controller decision,” no bounded state model for that wait, and no
deterministic reconciliation step linking a returned decision record to the
exact outstanding request. Without that artifact, a future controller
adapter/transport would have to redesign the governance model.

## Decision

Introduce a small `controller_handoff` module and a `controller-handoff` CLI
subcommand that creates, inspects, and reconciles local handoff requests under
`.agent_runner/controller_handoff/`.

Key choices:

1. **Orchestration artifact only.** A handoff request is not controller
   approval, owner approval, or permission to commit, push, merge, deploy,
   mutate lifecycle state, or impersonate the controller. It only records that
   a review bundle is waiting for a decision.

2. **Bounded safe metadata.** Each request contains only:
   - request version and request ID,
   - timestamp,
   - task ID and filename,
   - linked review-bundle path/reference,
   - review-bundle branch and pre/post HEAD evidence,
   - review-bundle recommended action,
   - handoff state,
   - reconciled controller-decision path and value when available,
   - audit reference when available.

   Full review bundle contents, full task bodies, worker transcripts,
   credentials, environment dumps, and customer/business data are excluded.

3. **Small explicit state model.**
   - `WAITING_DECISION` — a valid review bundle has been prepared for
     independent controller review.
   - `DECISION_RECEIVED` — a valid controller decision record has been
     reconciled to the request.
   - `BLOCKED` is reserved for future use when required handoff evidence is
     missing, malformed, conflicting, or unsafe.

4. **Fail-closed prepare.** A request is created only from a valid review
   bundle. Prepare fails closed when the bundle is missing, malformed, lacks
   task identity, carries an unsupported recommended action, or does not belong
   to the current branch.

5. **Deterministic reconciliation.** Reconciliation validates:
   - the request exists and parses,
   - the decision record exists and parses,
   - the decision actor is `controller` or `owner`, never `worker`,
   - decision and request task IDs and filenames agree,
   - the decision’s linked review-bundle reference matches the request’s bundle,
   - branch/pre/post HEAD evidence is consistent.

6. **No silent overwrite.** If a request is already reconciled to the same
   decision, reconciliation is idempotent. If it is already reconciled to a
   different decision, reconciliation fails closed.

7. **No lifecycle mutation.** Reconciliation updates only the local handoff
   request. It does not apply any task lifecycle transition; TASK-012 remains
   the only decision-to-lifecycle bridge.

8. **No Git publication.** Prepare and reconcile write only local
   `.agent_runner/` artifacts. They do not stage, commit, push, merge, deploy,
   switch branches, or access secrets.

9. **Audit extension.** New `mode: "handoff_prepare"` and
   `mode: "handoff_reconcile"` audit payloads record every prepare/reconcile
   attempt with safe metadata: task identity, request ID, state, bundle and
   decision references, branch, and HEAD. Full content, transcripts,
   credentials, and business data are excluded.

## Consequences

- The local runner now has an explicit machine-readable handoff contract
  between review-bundle production and controller-decision return.
- A future task can add a controller adapter or remote transport without
  redesigning request/decision linkage or governance rules.
- Workers cannot impersonate controllers; worker-authored decisions are
  rejected at reconciliation.
- Missing, malformed, inconsistent, or conflicting evidence fails closed.
- Handoff audit records provide local traceability independent of the
  decision-record audit and lifecycle-bridge audit trails.

## Alternatives considered

- **Implicit handoff via latest bundle and latest decision matching.**
  Rejected: deterministic linkage by path and identity evidence is safer and
  easier to audit than relying on timestamp coincidence.
- **Automatically create a handoff request after every `execute()` run.**
  Rejected: the handoff request is an explicit opt-in orchestration artifact.
  Automatic creation would conflate runner execution with controller handoff.
- **Allow the handoff request to store a copy of the review bundle body.**
  Rejected: the request stores only bounded metadata and a reference to the
  bundle, preserving the safe-field policy and avoiding content duplication.
- **Apply lifecycle transitions during reconciliation.** Rejected: TASK-012
  remains the sole decision-to-lifecycle bridge. Reconciliation is strictly
  an orchestration step.

## Compliance / risks

- No production data, secrets, or production databases are accessed.
- No schema changes or migrations were introduced.
- No Git commit/push/merge/branch-switch/deployment behavior was added.
- Handoff artifacts exclude full task bodies, worker transcripts, credentials,
  environment dumps, and business/customer data.
- A worker cannot use the handoff queue to self-approve.
