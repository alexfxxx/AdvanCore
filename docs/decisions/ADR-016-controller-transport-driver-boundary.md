# ADR-016 — Controller Transport-Driver Boundary

## Status

Accepted — implemented as part of TASK-016.

## Context

TASK-015 froze a transport-neutral controller request/response envelope around
the TASK-014 controller-adapter boundary. The envelope defines safe fields,
correlation, validation, and local file round-trip, but it intentionally does
not choose or implement a delivery mechanism.

Before adding any real remote transport (HTTP, webhook, queue, etc.), we need a
small boundary that separates envelope semantics from delivery mechanics. This
lets future transports be plugged in without changing controller authority,
handoff reconciliation, lifecycle authority, or Git-publication governance.

## Decision

Introduce a transport-driver abstraction plus one bounded local-filesystem
implementation:

- `ControllerTransportDriver` abstract contract with three operations:
  - `send(request)` — write a validated TASK-015 request envelope.
  - `receive(request)` — load a validated TASK-015 response envelope bound to
    the request.
  - `show(request_id)` — read-only inspection of driver artifacts.
- `LocalFilesystemTransportDriver` as the only built-in driver.
  - Requests live under `.agent_runner/controller_transport/outbox/`.
  - Responses live under `.agent_runner/controller_transport/inbox/`.
  - Deterministic filenames, idempotent identical resends, fail-closed
    conflicts, path traversal/symlink rejection, and no network or subprocess
    usage.

The driver is delivery plumbing only. It does not create, infer, approve,
reconcile, apply, publish, or deploy. A `DECISION_RECEIVED` response returned by
the driver still requires the existing TASK-011/TASK-013/TASK-014/TASK-015
validation/reconciliation path before any lifecycle action.

## Consequences

- Future remote transports can be added by implementing `ControllerTransportDriver`
  and serializing the existing TASK-015 envelope over the approved mechanism.
- Controller authority, envelope semantics, handoff reconciliation, lifecycle
  authority, and Git-publication governance remain unchanged.
- The local-filesystem driver gives us a deterministic, testable round-trip
  without introducing HTTP, webhooks, sockets, queues, credentials, or
  background processes.
- Driver operations stay local and auditable with the existing
  `mode: "controller_transport"` audit payload.

## Rejected alternatives

- **Directly add HTTP/webhook/queue transport now** — rejected because the task
  explicitly outlaws remote transport and choosing a mechanism or credential
  policy requires a future owner decision.
- **Embed driver logic inside `controller_transport.py`** — rejected because
  TASK-015 owns envelope semantics; TASK-016 owns delivery mechanics. Keeping
  them in separate modules preserves replaceability and clarity.
- **Make the driver responsible for reconciling decisions** — rejected because
  that would grant the driver controller authority. Reconciliation remains with
  the existing TASK-013 handoff reconciliation and TASK-015 response-application
  helpers.
