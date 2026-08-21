# TASK-015 — Controller Transport Envelope Foundation

STATUS: READY

## Objective

Create a deterministic, bounded, transport-neutral controller request/response envelope around the TASK-014 controller-adapter boundary so a future remote controller transport can exchange safe artifacts without redesigning controller authority, handoff, decision, lifecycle, or Git-publication semantics.

This task defines serialization, validation, correlation, and local file round-trip only. It must NOT add HTTP, webhooks, sockets, background polling, OpenAI/ChatGPT API calls, Kimi/Gemini/model calls as controller, credentials, or subprocess transport.

## Business context

The control-plane flow is now:

`GitHub Task → Local Agent Runner → Kimi worker → verification → review bundle → controller handoff → controller adapter → controller decision → decision/lifecycle bridge`

TASK-014 established a replaceable controller-adapter boundary and deliberately left remote/network transport out of scope. The next safe step is to freeze a transport-neutral envelope contract before any external transport is introduced.

The envelope must carry only bounded safe metadata/references already authorized by TASK-010/TASK-013/TASK-014. It is transport data, not authority and not approval.

## In scope

1. Add a focused module under `advancore/agent_runner/`, preferably `controller_transport.py`.
2. Define versioned request and response envelope models suitable for deterministic JSON serialization.
3. Request envelope must include only bounded safe fields, at minimum:
   - schema/version;
   - unique correlation/request id;
   - task identity;
   - handoff request reference;
   - review-bundle reference;
   - adapter name/type;
   - safe bounded controller evidence/metadata;
   - created timestamp if consistent with existing artifact conventions.
4. Response envelope must include only bounded safe fields, at minimum:
   - schema/version;
   - matching correlation/request id;
   - task identity;
   - result state limited to TASK-014 semantics (`PENDING`, `DECISION_RECEIVED`, `BLOCKED`);
   - controller-decision record reference/path when present;
   - bounded failure/blocking messages.
5. Provide deterministic JSON serialize/load/validate helpers.
6. Provide local file write/load helpers under a bounded ignored `.agent_runner/controller_transport/` location if needed.
7. Fail closed on unknown versions, unknown states, malformed JSON, missing required fields, mismatched task/correlation/handoff/review references, unsafe fields, or path escape attempts.
8. Do not embed full task bodies, worker transcripts, arbitrary repository files, environment dumps, credentials, connection strings, secrets, customer data, or arbitrary command output.
9. Add an orchestration helper that converts a validated TASK-013/TASK-014 handoff/input into a request envelope without changing authority semantics.
10. Add a response-validation helper that can convert a valid response envelope into a bounded TASK-014 adapter result or equivalent existing representation, delegating controller-decision validation/reconciliation to existing TASK-011/TASK-013/TASK-014 logic rather than duplicating it.
11. A response envelope must never itself be treated as an approval or lifecycle authorization.
12. Add safe CLI support for local envelope operations, for example:
    - `controller-transport request <handoff-or-latest>`
    - `controller-transport show <path-or-latest>`
    - `controller-transport validate-response <path>`
    Exact names may vary if a smaller compatible interface is clearer.
13. Inspection/show operations must be read-only.
14. Request generation may write only bounded local `.agent_runner/` artifacts/audit metadata; no Git index, lifecycle, database, branch, remote, deployment, or decision mutation.
15. Add deterministic tests for schema/version handling, serialization round-trip, correlation, safe-field policy, malformed/unknown data, path safety, request construction, response conversion, authority separation, read-only inspection, audit behavior, and absence of Git/lifecycle side effects.
16. Update `docs/architecture/AGENT_RUNNER.md` and add an ADR if appropriate.
17. Run the full pytest suite.
18. Complete this task-file Completion report and stop without committing or pushing.

## Important governance rule

A transport envelope is data exchange only. It is NOT controller authority.

It must never:

- make Kimi/worker a controller;
- infer or fabricate `APPROVE`;
- treat `DECISION_RECEIVED` as sufficient authority without a separately valid TASK-011 controller decision record;
- bypass TASK-013 reconciliation;
- bypass TASK-012 lifecycle authority;
- stage, commit, push, merge, deploy, or switch branches;
- access secrets/credentials;
- execute external commands or network calls.

## Explicitly out of scope

- OpenAI/ChatGPT API integration.
- Kimi/Gemini/other model integration as controller.
- HTTP clients or servers.
- Webhooks, sockets, queues, message brokers, email, Slack, or GitHub Issues/PR transport.
- Background polling/daemons.
- Secret/token/key handling.
- Automatic controller decision creation.
- Automatic lifecycle apply.
- Automatic Git publication/deployment.
- Database/model/migration changes.
- Cryptographic signing/identity.

## Database impact

None. No schema, model, migration, or production database change is authorized.

## Safety requirements

- Read and obey `AGENTS.md`.
- Stay on `agent-control-foundation`.
- `main` remains untouched and non-executable.
- Reuse TASK-010 through TASK-014 validation/authority helpers wherever practical.
- Existing TASK-011 actor restrictions remain unchanged.
- Existing TASK-012 lifecycle bridge remains the only decision → lifecycle bridge.
- Existing TASK-013 reconciliation remains authoritative for handoff/decision linkage.
- Existing TASK-014 adapter boundary remains transport/orchestration only.
- Unknown, stale, malformed, conflicting, mismatched, unauthorized, or unsafe evidence fails closed.
- Keep changes small, reversible, standard-library-first, and dependency-free unless already available.

## Acceptance criteria

- [ ] Versioned transport-neutral request envelope exists.
- [ ] Versioned transport-neutral response envelope exists.
- [ ] JSON serialization/deserialization is deterministic and tested.
- [ ] Correlation/request id is explicit and validated.
- [ ] Request input is bounded to safe TASK-013/TASK-014 evidence/references.
- [ ] Full task/worker/repository/secrets content is absent.
- [ ] Response state is limited to `PENDING`, `DECISION_RECEIVED`, `BLOCKED`.
- [ ] Unknown schema versions/states fail closed.
- [ ] Task/correlation/reference mismatches fail closed.
- [ ] Path traversal/escape is rejected for local envelope artifacts.
- [ ] Response envelope alone cannot authorize approval/lifecycle mutation.
- [ ] Valid returned decision still flows through existing TASK-011/TASK-013/TASK-014 validation/reconciliation.
- [ ] No network/API/subprocess transport exists.
- [ ] Inspection is read-only.
- [ ] No Git/lifecycle/database/deployment mutation occurs from envelope operations.
- [ ] Operations are locally auditable when applicable.
- [ ] No database/model/migration changes are made.
- [ ] Existing tests remain passing.
- [ ] Full pytest suite passes.
- [ ] Architecture documentation is updated.
- [ ] Completion report is written into this task file.

## Test requirements

At minimum test:

1. Valid handoff/input → bounded request envelope.
2. Request JSON write/load round-trip preserves deterministic fields.
3. Response JSON write/load round-trip preserves deterministic fields.
4. Missing/unknown schema version → rejected.
5. Unknown response state → rejected.
6. Missing/mismatched correlation id → rejected.
7. Task mismatch → rejected.
8. Handoff/review reference mismatch → rejected.
9. Unsafe/prohibited full-content fields → rejected or absent by construction.
10. Path traversal/escape → rejected.
11. `PENDING` response creates no decision/lifecycle authority.
12. `BLOCKED` response creates no decision/lifecycle authority.
13. `DECISION_RECEIVED` without a valid TASK-011 decision record → rejected/blocked.
14. Valid matching decision reference delegates to existing validation/reconciliation logic.
15. Worker-authored/unauthorized decision remains rejected.
16. Read-only show/inspection does not mutate artifacts, Git, or lifecycle state.
17. Request generation does not mutate Git HEAD/index/branch/remotes or task lifecycle.
18. Audit-write failure is explicit if audit is used.
19. Existing TASK-009 through TASK-014 tests and non-runner tests remain passing.

Run:

```bash
.venv/bin/python -m pytest tests/ -v
```

## Constraints

- Inspect TASK-010 review bundle, TASK-011 controller decision, TASK-012 lifecycle bridge, TASK-013 handoff, and TASK-014 controller adapter before coding.
- Do not modify `main`.
- Do not commit or push until explicit reviewer approval.
- Do not introduce network services, API calls, webhooks, credentials, background processes, or external subprocess execution.
- Do not invent a new controller authority model.
- If a new owner-level policy or credential/transport decision appears necessary, stop and report it.

## Owner decisions

None required to begin.

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

---

**Implemented**

- Added `advancore/agent_runner/controller_transport.py` defining a versioned,
  transport-neutral controller request/response envelope around the TASK-014
  controller-adapter boundary.
- Defined `ControllerTransportRequest` and `ControllerTransportResponse`
  dataclasses with bounded safe fields only: schema/version, correlation/request
  ID, task identity, handoff request reference, review-bundle reference, adapter
  name/type, bounded bundle evidence/metadata, and result state limited to
  `PENDING`, `DECISION_RECEIVED`, `BLOCKED`.
- Added deterministic JSON serialize/load/validate helpers that fail closed on
  unknown versions, unknown schemas, unknown states, malformed JSON, missing
  required fields, and correlation/reference mismatches.
- Added local file write/load helpers under `.agent_runner/controller_transport/`
  with sanitized filenames and path-traversal rejection.
- Added `handoff_to_transport_request()` orchestration helper that converts a
  validated TASK-013/TASK-014 handoff into a request envelope without changing
  authority semantics.
- Added `convert_response_to_adapter_result()` and `apply_transport_response()`
  helpers. `apply_transport_response()` delegates controller-decision
  validation/reconciliation to existing TASK-013 logic when a response reports
  `DECISION_RECEIVED` with a decision path.
- Added `build_controller_transport_audit_payload()` to `audit.py` and wired
  transport operations into the local audit trail with `mode: "controller_transport"`.
- Added `controller-transport` CLI subcommand in `__main__.py` with `request`,
  `show`, and `validate-response` commands.
- Added `tests/test_controller_transport.py` with 50 deterministic tests covering
  construction, serialization round-trip, validation, correlation/reference
  mismatches, safe-field policy, path safety, authority separation,
  reconciliation delegation, read-only inspection, audit behavior, and absence
  of Git/lifecycle side effects.
- Updated `docs/architecture/AGENT_RUNNER.md` with module description, updated
  flow diagram, envelope section, CLI usage, testing approach, threat
  boundaries, and FACT entries.
- Added `docs/decisions/ADR-015-controller-transport-envelope.md` documenting
  the architectural decision.

**Files changed**

- `advancore/agent_runner/controller_transport.py` (new)
- `advancore/agent_runner/audit.py`
- `advancore/agent_runner/__main__.py`
- `tests/test_controller_transport.py` (new)
- `docs/architecture/AGENT_RUNNER.md`
- `docs/decisions/ADR-015-controller-transport-envelope.md` (new)
- `tasks/TASK-015-controller-transport-envelope-foundation.md`

**Database changes**

None. No schema, model, migration, or production database change was authorized
or made.

**Tests executed and results**

```bash
.venv/bin/python -m pytest tests/ -v
```

Result: **322 passed in 5.92s** (272 pre-existing + 50 new transport-envelope tests).
All existing TASK-009 through TASK-014 tests remain passing.

**Assumptions**

- Future remote controller transports will consume the JSON envelope contract
  defined here rather than bypassing it.
- The existing `.agent_runner/` gitignore rule is sufficient to keep transport
  envelope artifacts out of the repository index.

**Risks / unresolved issues**

- The envelope does not include cryptographic signing or checksums. If
  tamper-evident handoff becomes a requirement, a future task should add it.
- The envelope is local-file-only in this task; actual network transport is
  untested by design (out of scope).

**Decisions required**

None. No owner-level policy or credential/transport decisions are required to
begin or complete this task.

**Recommended next step**

- Review and approve this task.
- Optional future task: implement an approved remote controller transport
  adapter that consumes this envelope contract over an approved network
  mechanism (e.g. HTTP, webhook, queue) while preserving TASK-011/TASK-012/
  TASK-013/TASK-014 authority boundaries.

**`git status --short`**

```
 M advancore/agent_runner/__main__.py
 M advancore/agent_runner/audit.py
 M docs/architecture/AGENT_RUNNER.md
?? advancore/agent_runner/controller_transport.py
?? docs/decisions/ADR-015-controller-transport-envelope.md
?? tests/test_controller_transport.py
```
