# ADR-015 — Controller Transport Envelope

## Status

Approved and implemented as part of TASK-015.

## Context

TASK-014 established a replaceable `ControllerAdapter` boundary between the local
handoff queue and an independent controller. The boundary intentionally left
remote/network transport out of scope so that authority, handoff, decision,
lifecycle, and Git-publication semantics could stabilize first.

The next safe step is to freeze a transport-neutral envelope contract before any
external transport is introduced. Without such a contract, a future remote
transport would have to redesign or bypass the existing governance layers to
exchange artifacts, increasing coupling and risking authority drift.

## Decision

Introduce a small `controller_transport` module and a `controller-transport` CLI
subcommand that defines versioned request/response envelopes, deterministic JSON
serialization, fail-closed validation, local file round-trip helpers, and a
response application helper that delegates decision reconciliation to existing
TASK-013 logic.

Key choices:

1. **Transport-neutral envelope, not transport implementation.** The envelope is
   a bounded JSON contract. It does not implement HTTP, webhooks, sockets,
   queues, background polling, model calls, credentials, or subprocess transport.

2. **Bounded safe fields only.**
   - Request envelope: envelope version/schema, unique correlation/request ID,
     timestamp, task identity, source handoff path/ID, linked review-bundle path,
     target adapter name/type, and bounded bundle evidence (branch, pre/post HEAD,
     recommended action, handoff state).
   - Response envelope: envelope version/schema, matching correlation/request ID,
     timestamp, task identity, source handoff path, linked review-bundle path,
     result state (`PENDING`, `DECISION_RECEIVED`, `BLOCKED`), optional
     controller-decision record reference/path and decision value, and bounded
     messages.

3. **Data exchange only, not authority.** The envelope never makes a worker a
   controller, infers `APPROVE`, treats `DECISION_RECEIVED` as sufficient
   authority without a separately valid TASK-011 decision record, or bypasses
   TASK-012 lifecycle authority or TASK-013 handoff reconciliation.

4. **Fail-closed validation.** Unknown envelope versions, unknown schemas,
   unknown response states, malformed JSON, missing required fields, and
   mismatched correlation/task/handoff/bundle references are all rejected.

5. **Path safety.** Envelope artifact paths are resolved against the repository
   root and rejected if they escape it. Generated filenames are sanitized.

6. **Delegation to existing reconciliation.** `apply_transport_response()`
   converts a valid response envelope to a bounded adapter result and, when the
   state is `DECISION_RECEIVED` with a decision path, reconciles the decision
   through the existing TASK-013 `reconcile_controller_handoff()` function. No
   reconciliation rules are duplicated in the transport layer.

7. **No lifecycle bridge invocation.** Transport response application does not
   call the TASK-012 `apply_controller_decision()` bridge and does not mutate
   task lifecycle state.

8. **No Git publication.** Envelope operations do not stage, commit, push,
   merge, deploy, switch branches, or access secrets.

9. **Read-only inspection.** `controller-transport show` loads and displays a
   request or response envelope. It does not reconcile decisions, write
   artifacts, or mutate task/Git/database state.

10. **Audit extension.** A new `mode: "controller_transport"` audit payload
    records envelope request and response application attempts with safe
    metadata: task identity, transport request ID, result state, handoff and
    decision references, reconciliation flag, branch, and HEAD. Full content,
    transcripts, credentials, and business data are excluded.

## Consequences

- The local runner now has a deterministic, bounded, transport-neutral envelope
  that future remote controller transports can consume without redesigning
  governance.
- Request and response artifacts are auditable, portable, and fail-closed on
  version/schema/state/reference mismatches.
- Workers cannot use the transport envelope to self-approve; returned decisions
  are still validated and reconciled through TASK-013.
- The envelope excludes full task bodies, worker transcripts, credentials,
  environment dumps, secrets, and customer/business data by construction.
- Transport envelope audit records provide local traceability independent of
  the handoff, decision-record, adapter, and lifecycle-bridge audit trails.

## Alternatives considered

- **Embed the full review bundle or task body in the envelope.** Rejected: the
  envelope carries only bounded references and metadata to preserve the existing
  safe-field policy and limit exposure.
- **Implement HTTP/webhook transport in this task.** Rejected: network transport
  is explicitly out of scope for TASK-015.
- **Treat the response envelope as a controller decision record.** Rejected: the
  response is data exchange only; authority still requires a separately valid
  TASK-011 decision record reconciled through TASK-013.
- **Add inline decision content to the response envelope.** Rejected: the
  response carries only a decision record reference/path so that existing
  TASK-011 validation and TASK-013 reconciliation remain authoritative.

## Compliance / risks

- No production data, secrets, or production databases are accessed.
- No schema changes or migrations were introduced.
- No Git commit/push/merge/branch-switch/deployment behavior was added.
- Envelope artifacts and audit records exclude full task bodies, worker
  transcripts, credentials, environment dumps, secrets, and business/customer
  data.
- A worker cannot use the transport envelope to self-approve; worker-authored
  decisions are rejected at reconciliation.
