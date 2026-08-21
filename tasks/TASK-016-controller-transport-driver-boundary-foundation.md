# TASK-016 — Controller Transport Driver Boundary Foundation

STATUS: READY

## Objective

Create a deterministic, replaceable controller transport-driver boundary around the TASK-015 transport-envelope contract so future network transports can be added without changing controller authority, envelope semantics, handoff reconciliation, lifecycle authority, or Git-publication governance.

This task adds a transport-driver abstraction plus one bounded local filesystem implementation only. It must NOT add HTTP, webhooks, sockets, queues, background polling, model/API calls, credentials, subprocess transport, or remote controller execution.

## Business context

The governed control-plane flow is now:

`GitHub Task → Local Agent Runner → Kimi worker → verification → review bundle → controller handoff → controller adapter → transport envelope → controller decision → reconciliation → lifecycle bridge`

TASK-014 established the controller-adapter boundary. TASK-015 froze a versioned transport-neutral request/response envelope. The next safe step is to separate envelope semantics from delivery mechanics through a small driver interface before any real remote transport is chosen.

The driver is delivery plumbing only. It is not controller authority and must never create, infer, approve, reconcile, apply, publish, or deploy on its own.

## In scope

1. Add `advancore/agent_runner/controller_transport_driver.py`.
2. Define a small replaceable transport-driver contract, preferably a `Protocol` or abstract interface, with bounded operations equivalent to:
   - send/write a validated TASK-015 request envelope;
   - receive/load a TASK-015 response envelope for a specific request/correlation id;
   - inspect driver state/artifact references without mutation where practical.
3. Add one local filesystem driver implementation under a bounded ignored location such as:
   - `.agent_runner/controller_transport/outbox/`
   - `.agent_runner/controller_transport/inbox/`
   Exact directory names may vary if a smaller safer structure is clearer.
4. Reuse TASK-015 envelope serialization, path validation, request/response validation, and response-application helpers. Do not duplicate envelope authority or reconciliation rules.
5. Driver send must accept only an already-valid `ControllerTransportRequest` (or validate through the existing TASK-015 helper before writing).
6. Driver receive must return only an already-valid `ControllerTransportResponse` bound to the expected task, correlation/request id, handoff reference, and review-bundle reference.
7. Fail closed on malformed files, unknown schema/version/state, wrong correlation id, task mismatch, stale/mismatched references, path escape, symlink/path traversal escape, ambiguous multiple responses, or unexpected artifact type.
8. File creation/writes must be deterministic, bounded, and idempotent where safe. Re-sending the identical request must not silently create conflicting divergent artifacts.
9. A conflicting existing request/response for the same correlation id must block rather than overwrite silently.
10. Driver inspection/list/show operations must be read-only.
11. Driver send/receive must not invoke TASK-012 lifecycle mutation.
12. Driver receive must not treat `DECISION_RECEIVED` as approval. Any returned decision reference still requires existing TASK-011/TASK-013/TASK-014/TASK-015 validation/reconciliation.
13. Add focused CLI support under the existing `controller-transport` command or a clearly bounded sibling command for local driver operations, for example:
    - `controller-transport driver-send <request-or-latest>`
    - `controller-transport driver-receive <request-or-id>`
    - `controller-transport driver-show <request-or-id>`
    Exact names may vary if a smaller compatible interface is clearer.
14. CLI driver operations must remain local-only and must not access network, credentials, Git remotes, databases, or subprocess transports.
15. Reuse existing controller-transport audit behavior where appropriate. If additional audit metadata is necessary, keep it bounded to safe identifiers/references only and do not broaden audit content.
16. Add deterministic tests covering interface behavior, local driver round-trip, idempotency/conflict behavior, correlation/reference binding, path safety, read-only inspection, fail-closed behavior, authority separation, and absence of Git/lifecycle/network side effects.
17. Update `docs/architecture/AGENT_RUNNER.md` and add `docs/decisions/ADR-016-controller-transport-driver-boundary.md`.
18. Run the full pytest suite.
19. Complete this task-file Completion report and stop without committing or pushing.

## Important governance rule

A transport driver moves validated envelope artifacts. It does NOT possess controller authority.

It must never:

- make Kimi/worker a controller;
- create or fabricate a controller decision;
- infer `APPROVE` from transport success;
- treat file presence as approval;
- bypass TASK-011 decision validation;
- bypass TASK-013 handoff reconciliation;
- bypass TASK-012 lifecycle authority;
- stage, commit, push, merge, deploy, or switch branches;
- execute external commands or network calls;
- access credentials, tokens, secrets, environment dumps, customer data, or production data.

## Explicitly out of scope

- HTTP/HTTPS client or server.
- Webhooks.
- WebSocket/socket transport.
- Message queues/brokers.
- Email, Slack, GitHub Issues/PR transport.
- OpenAI/ChatGPT API integration.
- Kimi/Gemini/other model integration as controller.
- Background polling, daemons, schedulers, file watchers, or long-running services.
- Credentials, API keys, tokens, secret storage, auth, or OAuth.
- Cryptographic signing/identity.
- Automatic controller decision creation.
- Automatic lifecycle apply.
- Automatic Git publication/deployment.
- Database/model/migration changes.

## Allowed changed-file scope

The worker may change only these seven paths unless it stops and reports why an additional path is required:

1. `advancore/agent_runner/controller_transport_driver.py` (new)
2. `advancore/agent_runner/__init__.py`
3. `advancore/agent_runner/__main__.py`
4. `tests/test_controller_transport_driver.py` (new)
5. `docs/architecture/AGENT_RUNNER.md`
6. `docs/decisions/ADR-016-controller-transport-driver-boundary.md` (new)
7. `tasks/TASK-016-controller-transport-driver-boundary-foundation.md`

No other file is authorized for modification in TASK-016. If implementation genuinely requires another file, stop before changing it and report the need for reviewer approval.

## Database impact

None. No schema, model, migration, or production database change is authorized.

## Safety requirements

- Read and obey `AGENTS.md`.
- Stay on `agent-control-foundation`.
- `main` remains untouched and non-executable.
- Reuse TASK-013 through TASK-015 validation/authority helpers wherever practical.
- Existing TASK-011 actor restrictions remain unchanged.
- Existing TASK-012 lifecycle bridge remains the only decision → lifecycle bridge.
- Existing TASK-013 reconciliation remains authoritative for handoff/decision linkage.
- Existing TASK-014 controller adapter remains orchestration only.
- Existing TASK-015 envelope validation remains authoritative for envelope semantics.
- Unknown, stale, malformed, conflicting, mismatched, unauthorized, ambiguous, or unsafe evidence fails closed.
- Keep changes small, reversible, standard-library-first, and dependency-free unless already available.

## Acceptance criteria

- [ ] Replaceable controller transport-driver contract exists.
- [ ] Local filesystem driver implementation exists.
- [ ] Driver consumes TASK-015 request/response envelope types rather than inventing a second envelope model.
- [ ] Send path validates request and writes only under the bounded local transport directory.
- [ ] Receive path validates response and binds it to expected task/correlation/handoff/review references.
- [ ] Identical request resend is deterministic/idempotent or explicitly safe.
- [ ] Conflicting duplicate artifacts fail closed and are not silently overwritten.
- [ ] Missing/ambiguous/malformed responses fail closed.
- [ ] Path traversal, symlink escape, and repository-root escape are rejected.
- [ ] Inspection operations are read-only.
- [ ] Transport success is never interpreted as controller approval.
- [ ] `DECISION_RECEIVED` still requires existing controller-decision validation/reconciliation.
- [ ] No lifecycle mutation occurs from driver send/receive/show.
- [ ] No network/API/subprocess/background transport exists.
- [ ] No Git index/HEAD/branch/remote mutation occurs.
- [ ] No database/model/migration changes occur.
- [ ] Full task bodies, worker transcripts, secrets, credentials, environment dumps, customer data, and arbitrary repository content are not copied into driver artifacts.
- [ ] Existing tests remain passing.
- [ ] Full pytest suite passes.
- [ ] Architecture documentation and ADR are updated.
- [ ] Exact seven-file changed scope is respected.
- [ ] Completion report is written into this task file.

## Test requirements

At minimum test:

1. Valid TASK-015 request → filesystem driver send succeeds.
2. Written request loads back as the same validated envelope.
3. Identical resend is deterministic/idempotent.
4. Divergent request with same correlation id → blocked.
5. Valid matching response → receive succeeds.
6. Missing response → bounded pending/not-found result or explicit fail-closed error, consistent with the chosen interface.
7. Malformed response JSON → rejected.
8. Unknown response schema/version/state → rejected through TASK-015 validation.
9. Correlation mismatch → rejected.
10. Task mismatch → rejected.
11. Handoff/review-bundle mismatch → rejected.
12. Ambiguous multiple response candidates → rejected.
13. Path traversal/root escape → rejected.
14. Symlink escape outside the bounded transport directory → rejected where platform support permits deterministic testing.
15. `PENDING` response creates no decision/lifecycle authority.
16. `BLOCKED` response creates no decision/lifecycle authority.
17. `DECISION_RECEIVED` alone does not authorize approval/lifecycle mutation.
18. Valid decision reference remains delegated to existing TASK-015/TASK-013 reconciliation helpers rather than duplicated in the driver.
19. CLI show/inspection is read-only.
20. Driver send/receive does not mutate Git HEAD/index/branch/remotes or task lifecycle.
21. No network/socket/subprocess calls are made.
22. Existing TASK-009 through TASK-015 tests and non-runner tests remain passing.

Run:

```bash
.venv/bin/python -m pytest tests/ -v
```

## Constraints

- Inspect TASK-013 handoff, TASK-014 adapter, TASK-015 envelope, `controller_transport.py`, and existing CLI/audit behavior before coding.
- Do not modify `main`.
- Do not commit or push until explicit reviewer approval.
- Do not introduce real remote transport, API calls, credentials, background processes, or external subprocess execution.
- Do not invent a new controller authority model.
- Do not expand beyond the exact seven-file scope without stopping for reviewer approval.

## Owner decisions

None required to begin.

A later real remote transport task WILL require an explicit owner choice of transport mechanism and authentication/credential policy before implementation.

## Completion report

To be completed by the worker. Report:

- Implemented
- Files changed
- Database changes
- Tests executed and results
- Assumptions
- Risks / unresolved issues
- Decisions required
- Recommended next step
- `git status --short`
