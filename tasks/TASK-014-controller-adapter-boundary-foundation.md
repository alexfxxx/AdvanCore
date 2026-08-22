# TASK-014 — Controller Adapter Boundary Foundation

STATUS: COMPLETED

## Objective

Create a replaceable controller-adapter boundary that can consume a validated TASK-013 controller-handoff request and return a bounded controller-adapter result without changing the existing review, decision, lifecycle, Git-publication, or authority rules.

This task defines the controller-side orchestration interface only. It must make future direct controller integration possible without redesigning the control plane, while keeping the current implementation local, fail-closed, and free of network/API/secrets requirements.

## Business context

The current control-plane flow is now:

`GitHub Task → Local Agent Runner → Kimi worker → post-worker verification → audit → review bundle → controller handoff request → controller decision record → decision/lifecycle bridge`

TASK-013 created a machine-readable local queue contract with `WAITING_DECISION`, `DECISION_RECEIVED`, and `BLOCKED` states. The remaining architectural gap is that there is no replaceable controller adapter analogous to the existing worker-adapter boundary.

Without an adapter boundary, any future integration with an independent controller would have to be wired directly into CLI/orchestration code, increasing coupling and risking governance drift.

TASK-014 introduces that boundary only. It does not yet add OpenAI/ChatGPT network integration or any other remote transport.

## Facts

- TASK-005 established a replaceable `WorkerAdapter` boundary for worker execution.
- TASK-010 produces trusted local review bundles under `.agent_runner/review/`.
- TASK-011 produces bounded controller decision records under `.agent_runner/decisions/`.
- TASK-012 is the only decision → lifecycle bridge.
- TASK-013 produces controller-handoff requests under `.agent_runner/controller_handoff/` and reconciles matching decision records.
- Handoff requests are orchestration artifacts only; they are not approval.
- Worker/Kimi cannot act as controller or owner.
- Commit, push, merge, deployment, branch switching, destructive actions, secrets access, and commercial/compliance changes remain separately gated.

## In scope

1. Add a focused controller-adapter module under `advancore/agent_runner/`, preferably `controller_adapter.py`.
2. Define a small replaceable adapter interface analogous in spirit to `WorkerAdapter`, but for independent controller handoff.
3. At minimum, the interface must represent:
   - adapter name/type;
   - a validated controller-handoff request as input;
   - bounded safe review evidence/reference sufficient for an independent controller;
   - a deterministic adapter result;
   - whether a controller decision was returned;
   - a controller-decision record path/reference when available;
   - clear failure/blocking messages.
4. Define an explicit adapter result state model. At minimum support:
   - `PENDING` — request is valid but no controller decision has been returned;
   - `DECISION_RECEIVED` — a valid controller decision has been returned/reconciled;
   - `BLOCKED` — adapter execution or returned evidence is missing, malformed, inconsistent, unauthorized, or unsafe.
5. Provide a safe built-in local/manual adapter implementation that:
   - validates the handoff request;
   - exposes/returns the bounded handoff information needed for an independent controller;
   - does not invent or synthesize a controller decision;
   - returns `PENDING` until a separately valid controller decision exists;
   - performs no network or external-process execution.
6. Permit test-only fake/stub adapters for deterministic unit tests.
7. Do not add an adapter that uses Kimi/worker as the controller.
8. Do not add a remote/network adapter in this task.
9. Do not execute arbitrary shell commands or subprocesses from the controller adapter in this task.
10. Add a controller-adapter orchestration helper that:
    - loads and validates a handoff request;
    - requires handoff state compatible with controller review;
    - invokes exactly one selected adapter;
    - validates the returned adapter result;
    - if a valid existing controller decision record is supplied/returned, validates and reconciles it through the existing TASK-013 handoff logic rather than duplicating reconciliation rules;
    - does not automatically invoke TASK-012 lifecycle apply.
11. Reuse existing TASK-011/TASK-013 validation helpers wherever practical. Do not create a parallel controller authority model.
12. Add CLI support with safe defaults, for example:
    - `controller-adapter dispatch <handoff-or-latest> --adapter manual`
    - `controller-adapter status <handoff-or-latest>`
    Exact command names may vary if a smaller compatible interface is clearer.
13. The default/built-in adapter must be `manual` (or equivalent safe local adapter) and must not contact any network service.
14. CLI output must clearly show:
    - adapter name;
    - task identity;
    - handoff request path and current handoff state;
    - review-bundle reference;
    - adapter result state;
    - decision path/reference when available;
    - whether reconciliation occurred;
    - audit reference/result when available.
15. `status`/inspection must be read-only.
16. Adapter dispatch may write only bounded local `.agent_runner/` audit/adapter artifacts if needed. It must not mutate task lifecycle state, Git index, commits, branches, remotes, deployment state, or database state.
17. Add local audit metadata for controller-adapter dispatch/result attempts using the existing audit architecture or a small compatible extension.
18. Add deterministic tests for interface behavior, manual adapter behavior, fake adapter behavior, result validation, worker/controller authority separation, handoff linkage, reconciliation delegation, read-only inspection, failure handling, audit behavior, and absence of Git/lifecycle side effects.
19. Update `docs/architecture/AGENT_RUNNER.md` and add an ADR if a material architectural decision is introduced.
20. Run the full pytest suite.
21. Complete the task-file Completion report and stop without committing or pushing.

## Important governance rule

A controller adapter is a transport/orchestration boundary, not an authority source.

It must never:

- make a worker into a controller;
- treat a handoff request as approval;
- fabricate an `APPROVE` decision;
- bypass TASK-011 controller-decision validation;
- bypass TASK-012 lifecycle authority;
- stage, commit, push, merge, deploy, or switch branches;
- access secrets or credentials;
- execute destructive Git/database operations.

A controller decision becomes authoritative only when represented by a separately valid TASK-011 controller decision record from an allowed actor (`controller` or `owner`). Any lifecycle mutation remains explicitly governed by TASK-012.

## Adapter contract requirements

The adapter boundary should be small and replaceable. A future task should be able to add another adapter without modifying lifecycle/review-bundle/controller-decision semantics.

At minimum, a controller adapter must not receive arbitrary repository contents. Its input should be limited to bounded handoff/review references and safe metadata already approved by TASK-010/TASK-013.

The manual adapter must not infer a decision from the review bundle recommendation. In particular:

- bundle recommendation `REVIEW` does not imply controller `APPROVE`;
- bundle recommendation `REWORK` does not by itself authorize a controller decision record;
- bundle recommendation `BLOCKED` does not replace independent controller review.

## Future-extension boundary

This task should make a future remote controller adapter straightforward, but must not implement one now.

Explicitly out of scope for TASK-014:

- OpenAI/ChatGPT API calls;
- Gemini/Kimi/other model calls as controller;
- HTTP clients or servers;
- webhooks;
- background polling;
- email/Slack transport;
- GitHub Issues/PR write integration;
- secret/token/key handling;
- arbitrary external-process execution.

If implementation appears to require any of these, stop and report rather than expanding scope.

## Out of scope

- Remote/network controller transport.
- Automatic controller invocation over a network.
- Automatic creation of an `APPROVE`, `REWORK`, or `BLOCKED` decision.
- Automatic lifecycle apply.
- Automatic Git staging, commit, push, merge, or deployment.
- Branch switching.
- Worker self-approval or controller impersonation.
- Secret/credential access.
- Database/model/migration changes.
- ERP/business feature work.
- Cryptographic identity/signing.
- General runner redesign.

## Database impact

None. No schema, model, migration, or production database change is authorized.

## Safety requirements

- Read and obey `AGENTS.md`.
- Stay on `agent-control-foundation`.
- `main` remains untouched and non-executable.
- Existing runner pre/post Git safety checks remain unchanged.
- Existing TASK-009 lifecycle authority remains the sole task-state authority.
- Existing TASK-011 controller actor restrictions remain unchanged.
- Existing TASK-012 lifecycle bridge remains the only decision → lifecycle bridge.
- Existing TASK-013 handoff reconciliation remains the source of truth for linking a returned decision to a request.
- The built-in controller adapter must perform no network calls, secret access, or subprocess execution.
- Unknown, missing, conflicting, stale, malformed, or unauthorized evidence must fail closed.
- No full task bodies, worker transcripts, environment dumps, arbitrary command output, credentials, connection strings, or customer/business operational data may be copied into adapter artifacts/audit output.
- Keep changes small and reversible.

## Acceptance criteria

- [ ] A replaceable controller-adapter interface exists.
- [ ] A safe built-in manual/local adapter exists.
- [ ] Manual adapter returns `PENDING` when no valid controller decision exists; it never invents approval.
- [ ] Test fake/stub adapters can deterministically return controlled results.
- [ ] Adapter result states are limited to `PENDING`, `DECISION_RECEIVED`, or `BLOCKED`.
- [ ] Invalid/unknown adapter result states fail closed.
- [ ] Worker/Kimi cannot be treated as controller through the adapter boundary.
- [ ] Adapter input is bounded to safe handoff/review evidence and references.
- [ ] A valid returned decision is processed through existing TASK-011/TASK-013 validation/reconciliation rather than duplicated authority logic.
- [ ] Adapter dispatch does not mutate lifecycle state automatically.
- [ ] Adapter dispatch/status does not stage, commit, push, merge, deploy, or switch branches.
- [ ] Built-in adapter performs no network/API call, secret access, or subprocess execution.
- [ ] Read-only status/inspection does not mutate Git/task/artifact state.
- [ ] Adapter operations are auditable locally.
- [ ] Write/audit/validation failures are explicit and tested.
- [ ] No database/model/migration changes are made.
- [ ] Existing runner, lifecycle, review-bundle, controller-decision, lifecycle-bridge, handoff, audit, and non-runner tests remain passing.
- [ ] Full pytest suite passes.
- [ ] Architecture documentation is updated.
- [ ] Completion report is written into this task file.

## Test requirements

At minimum test:

1. Valid `WAITING_DECISION` handoff + manual adapter → `PENDING`.
2. Manual adapter never creates or infers an `APPROVE` decision.
3. Valid bounded handoff metadata is exposed to the adapter; prohibited/full-content fields are absent.
4. Missing handoff request → rejected.
5. Malformed handoff request → rejected.
6. Unsupported handoff state → rejected or clearly handled according to documented rules.
7. Unknown adapter name/type → rejected.
8. Fake adapter + valid matching controller decision → `DECISION_RECEIVED` and reconciliation delegates to TASK-013 logic.
9. Fake adapter returns worker-authored controller decision → rejected / `BLOCKED`.
10. Fake adapter returns task-mismatched decision → rejected / `BLOCKED`.
11. Fake adapter returns bundle-reference mismatch → rejected / `BLOCKED`.
12. Fake adapter returns unknown result state → fail closed.
13. Adapter failure/exception → explicit `BLOCKED`/failure result without lifecycle/Git mutation.
14. Already reconciled handoff behavior is deterministic and tested.
15. Dispatch does not change task lifecycle status.
16. Dispatch does not change Git HEAD, branch, index, or remote state.
17. Read-only status/inspection does not mutate artifacts or Git/task state.
18. Audit record/reference is produced when available.
19. Audit-write failure is reported explicitly.
20. Existing TASK-009 through TASK-013 tests and non-runner tests remain passing.

Run:

```bash
.venv/bin/python -m pytest tests/ -v
```

## Constraints

- Read and obey `AGENTS.md`.
- Inspect existing `worker.py` adapter design, TASK-010 review bundle, TASK-011 controller decision, TASK-012 lifecycle bridge, and TASK-013 handoff queue before coding.
- Stay on `agent-control-foundation`.
- Do not modify `main`.
- Do not commit or push until explicit reviewer approval.
- Prefer standard-library support and existing project helpers over new dependencies.
- Do not introduce network services, API calls, webhooks, credentials, or external subprocess execution.
- If implementation requires a new owner-level authority or transport policy, stop and report it instead of inventing it.

## Owner decisions

None required to begin.

## Completion report

### Implemented

- Added `advancore/agent_runner/controller_adapter.py` with:
  - `ControllerAdapter` abstract boundary and built-in `ManualControllerAdapter`.
  - `FakeControllerAdapter` for deterministic unit tests.
  - Adapter registry (`register_controller_adapter`, `get_controller_adapter`).
  - `AdapterResultState` enum: `PENDING`, `DECISION_RECEIVED`, `BLOCKED`.
  - Bounded `ControllerAdapterInput` and `ControllerAdapterResult` models.
  - `dispatch_controller_adapter()` orchestration helper that loads a handoff request, invokes one adapter, validates the result state, and reconciles any returned decision through existing TASK-013 logic.
  - `inspect_controller_adapter_status()` read-only inspection helper.
  - `format_adapter_result()` human-readable formatter.
- Extended `advancore/agent_runner/audit.py` with `build_controller_adapter_audit_payload()` (mode `controller_adapter`).
- Extended `advancore/agent_runner/__main__.py` with `controller-adapter dispatch` and `controller-adapter status` CLI subcommands; default adapter is `manual`.
- Added `tests/test_controller_adapter.py` covering interface behavior, manual adapter, fake adapter, result validation, authority separation, handoff linkage, reconciliation delegation, read-only inspection, failure handling, audit behavior, and absence of Git/lifecycle side effects.
- Updated `docs/architecture/AGENT_RUNNER.md` with the new module, flow diagram, safety principle, CLI usage, testing approach, threat boundaries, and FACTs.
- Added `docs/decisions/ADR-014-controller-adapter-boundary.md` documenting the architectural decision.

### Files changed

- `advancore/agent_runner/__main__.py`
- `advancore/agent_runner/audit.py`
- `advancore/agent_runner/controller_adapter.py` (new)
- `docs/architecture/AGENT_RUNNER.md`
- `docs/decisions/ADR-014-controller-adapter-boundary.md` (new)
- `tests/test_controller_adapter.py` (new)
- `tasks/TASK-014-controller-adapter-boundary-foundation.md`

### Database changes

None. No schema, model, migration, or production database change was authorized or made.

### Tests and results

- New tests: `tests/test_controller_adapter.py` — 32 passed.
- Full suite: `.venv/bin/python -m pytest tests/ -v` — 272 passed, 0 failed.

### Assumptions

- Future remote controller adapters will implement the same `ControllerAdapter` interface and register themselves; the boundary is designed to make this straightforward without changing governance rules.
- The built-in `manual` adapter is sufficient for local fail-closed operation until a future task authorizes a network transport.

### Risks / unresolved issues

- None identified. The implementation stays within the scoped boundary and does not introduce network, secrets, subprocess, or lifecycle-mutation behavior.

### Decisions required

- None. All implementation decisions are documented in ADR-014 and are within the approved task scope.

### Recommended next step

- Reviewer approval of this task and the ADR.
- A future task may add a remote controller adapter (e.g., HTTP/API-based) on top of this boundary once policy and transport requirements are approved.

### git status --short

 M advancore/agent_runner/__main__.py
 M advancore/agent_runner/audit.py
 M docs/architecture/AGENT_RUNNER.md
?? advancore/agent_runner/controller_adapter.py
?? docs/decisions/ADR-014-controller-adapter-boundary.md
?? tests/test_controller_adapter.py
