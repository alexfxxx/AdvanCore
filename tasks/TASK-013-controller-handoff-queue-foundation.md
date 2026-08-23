# TASK-013 — Controller Handoff Queue Foundation

STATUS: READY

## Objective

Create a bounded local controller handoff queue that turns the existing review-bundle → controller-decision path into an explicit machine-readable request/response workflow.

The purpose is to remove terminal screenshots and ad-hoc copy/paste from the control-plane design while preserving all existing governance. This task creates the local queue/orchestration contract only. It does not add network transport, GitHub write actions, automatic controller invocation, automatic approval, commit, push, merge, deployment, or branch switching.

## Business context

The current control-plane flow is:

`GitHub Task → Local Agent Runner → Kimi worker → post-worker verification → audit → review bundle → controller decision record → decision/lifecycle bridge`

TASK-010 standardized the review evidence. TASK-011 standardized the independent controller decision record. TASK-012 safely bridges a validated decision into the existing lifecycle state machine.

The remaining courier problem is orchestration: the local runner has no explicit machine-readable object representing “this review bundle is waiting for an independent controller decision,” no deterministic queue/status model for that handoff, and no bounded reconciliation step linking a returned decision record to the exact outstanding request.

TASK-013 introduces that local handoff contract so a future controller adapter/transport can be added without redesigning the governance model.

## Facts

- Review bundles live under `.agent_runner/review/`.
- Controller decision records live under `.agent_runner/decisions/`.
- TASK-012 can preview/apply a validated decision to the existing task lifecycle.
- Review bundles may recommend only `REVIEW`, `REWORK`, or `BLOCKED`; never `APPROVED`.
- Controller decision values are `APPROVE`, `REWORK`, or `BLOCKED`.
- Worker/Kimi cannot act as controller or owner.
- Commit, push, merge, deployment, secrets access, destructive operations, and business/compliance rule changes remain separately gated.

## In scope

1. Add a local controller-handoff model under `advancore/agent_runner/`, preferably a new focused module such as `controller_handoff.py`.
2. Store handoff request artifacts under `.agent_runner/controller_handoff/` (or an equally clear repository-local gitignored subdirectory under `.agent_runner/`).
3. Use deterministic machine-readable JSON.
4. Define a small explicit handoff state model. At minimum support:
   - `WAITING_DECISION` — a valid review bundle has been prepared for independent controller review;
   - `DECISION_RECEIVED` — a valid controller decision record has been reconciled to the request;
   - `BLOCKED` — required handoff evidence is missing, malformed, conflicting, or unsafe.
5. A handoff request must include only bounded safe metadata, including:
   - request version,
   - request ID,
   - timestamp,
   - task ID and task filename,
   - review-bundle path/reference,
   - review-bundle branch,
   - pre/post HEAD evidence,
   - review-bundle recommended action,
   - handoff state,
   - controller-decision path/reference when reconciled,
   - resulting controller decision when reconciled,
   - audit reference when available.
6. Create requests only from a valid existing review bundle.
7. Fail closed if the review bundle is missing, malformed, has missing task identity, has an unsupported recommended action, or does not belong to the current branch.
8. Do not copy the full review bundle body into the request; store bounded fields/reference only.
9. Add deterministic reconciliation from an existing controller decision record to an outstanding handoff request.
10. Reconciliation must validate:
    - request exists and parses correctly,
    - decision record exists and parses correctly,
    - decision actor is controller or owner, never worker,
    - decision task identity matches request identity,
    - decision's linked review-bundle path/reference matches the request's review bundle,
    - branch/task evidence is consistent,
    - a request already reconciled to a different decision fails closed rather than being silently overwritten.
11. Reconciliation must not apply the lifecycle transition automatically. TASK-012 remains the only decision→lifecycle bridge.
12. Add CLI support with safe, explicit commands, for example:
    - `controller-handoff prepare <bundle-or-latest>`
    - `controller-handoff show <request-or-latest>`
    - `controller-handoff reconcile <request-or-latest> <decision-or-latest>`
    Exact command shape may vary if a simpler compatible interface is better.
13. `show` must be read-only.
14. `prepare` and `reconcile` may write only local `.agent_runner/` handoff/audit artifacts; they must not mutate task files, Git index, commits, branches, remotes, or database state.
15. CLI output must clearly report the handoff-request path and state.
16. Add local audit metadata for prepare/reconcile attempts using the existing audit architecture or a small compatible extension.
17. Add deterministic tests for request creation, state transitions, safe-field policy, linkage validation, malformed/missing evidence, branch mismatch, duplicate/conflicting reconciliation, read-only inspection, write failure, and audit behavior.
18. Update `docs/architecture/AGENT_RUNNER.md` and add an ADR if a material architectural decision is introduced.
19. Run the full pytest suite.
20. Complete the task-file Completion report and stop without committing or pushing.

## Important governance rule

A controller handoff request is an orchestration artifact only.

It must never be treated as:

- controller approval,
- owner approval,
- permission to commit or push,
- permission to merge or deploy,
- permission to mutate task lifecycle state,
- permission for Kimi/worker to impersonate the controller.

Only a separately validated controller decision record from TASK-011 can express `APPROVE`, `REWORK`, or `BLOCKED`, and TASK-012 remains responsible for any explicit lifecycle preview/apply.

## Future-extension boundary

This task should define the local handoff contract cleanly enough that a future task can add a controller adapter or remote transport without redesigning request/decision linkage.

Do not implement that transport now.

In particular, this task must not add:

- OpenAI/API calls,
- ChatGPT network integration,
- GitHub Issues/PR write integration,
- email/Slack transport,
- webhooks,
- background polling,
- secret/token handling.

If the implementation appears to require any of those, stop and report rather than expanding scope.

## Out of scope

- Automatic controller invocation.
- Remote/network transmission of review bundles or handoff requests.
- GitHub write actions from the runner.
- Automatic creation of controller decisions.
- Automatic lifecycle apply.
- Automatic staging, commit, push, merge, or deployment.
- Branch switching.
- Worker self-approval or controller impersonation.
- Secret/credential access.
- Database/model/migration changes.
- ERP/business feature work.
- Cryptographic signing or identity.
- General runner redesign.

## Database impact

None. No schema, model, migration, or production database change is authorized.

## Safety requirements

- Read and obey `AGENTS.md`.
- Stay on `agent-control-foundation`.
- `main` remains untouched and non-executable.
- Existing pre/post Git safety checks remain unchanged.
- Existing TASK-009 lifecycle authority remains the sole task-state authority.
- Existing TASK-011 controller actor restrictions remain unchanged.
- Existing TASK-012 lifecycle bridge remains the only decision→lifecycle bridge.
- Handoff artifacts must remain repository-local under `.agent_runner/` and gitignored.
- No secrets, environment dumps, connection strings, full task bodies, full worker transcripts, arbitrary command output, or customer/business operational data may be stored in handoff artifacts.
- Unknown, missing, conflicting, stale, or malformed evidence must fail closed.
- Keep changes small and reversible.

## Acceptance criteria

- [ ] A valid review bundle can create one deterministic local controller-handoff request.
- [ ] New requests start in `WAITING_DECISION`.
- [ ] A valid matching controller decision can be reconciled to the request.
- [ ] Successful reconciliation moves the request to `DECISION_RECEIVED`.
- [ ] Missing/malformed/conflicting evidence fails closed and is reported clearly.
- [ ] Worker-authored controller decisions are rejected.
- [ ] Request/decision task identity mismatch is rejected.
- [ ] Review-bundle reference mismatch is rejected.
- [ ] Current branch mismatch is rejected during prepare where branch evidence is available.
- [ ] Reconciliation cannot silently replace a different existing decision.
- [ ] Handoff records contain only bounded safe metadata.
- [ ] Full review bundle/task/transcript contents are not copied into handoff artifacts.
- [ ] Read-only inspection does not mutate Git or task state.
- [ ] Prepare/reconcile do not mutate task lifecycle state.
- [ ] Prepare/reconcile do not stage, commit, push, merge, deploy, switch branches, or access secrets.
- [ ] Handoff operations are auditable locally.
- [ ] Write failures are explicit and tested.
- [ ] No database/model/migration changes are made.
- [ ] Existing runner, lifecycle, review-bundle, controller-decision, bridge, audit, and non-runner tests remain passing.
- [ ] Full pytest suite passes.
- [ ] Architecture documentation is updated.
- [ ] Completion report is written into this task file.

## Test requirements

At minimum test:

1. Valid review bundle → request created in `WAITING_DECISION`.
2. Request contains correct task/bundle/branch/HEAD/recommendation metadata.
3. Request excludes sensitive/full-content fields.
4. Missing review bundle → rejected.
5. Malformed review bundle → rejected.
6. Unsupported/malformed bundle recommendation → rejected.
7. Current branch mismatch on prepare → rejected.
8. Valid controller decision matching request → reconciliation succeeds and state becomes `DECISION_RECEIVED`.
9. Worker actor decision → reconciliation rejected.
10. Task ID mismatch → rejected.
11. Task filename mismatch → rejected.
12. Review-bundle reference mismatch → rejected.
13. Missing/malformed decision record → rejected.
14. Request already linked to same decision → deterministic/idempotent behavior is defined and tested.
15. Request already linked to a different decision → fail closed; no silent overwrite.
16. Read-only `show` does not change Git status, HEAD, task state, or artifact contents.
17. Prepare/reconcile do not mutate task files or Git publication state.
18. Audit record/reference is produced when available.
19. Handoff write failure is explicit.
20. Existing TASK-009 through TASK-012 tests and non-runner tests remain passing.

Run:

```bash
.venv/bin/python -m pytest tests/ -v
```

## Constraints

- Read and obey `AGENTS.md`.
- Inspect TASK-010 review bundle, TASK-011 controller decision, and TASK-012 lifecycle bridge before coding.
- Stay on `agent-control-foundation`.
- Do not modify `main`.
- Do not commit or push until explicit reviewer approval.
- Prefer standard-library JSON/path/time support and existing helpers over new dependencies.
- Do not introduce network services, external API calls, webhooks, or credentials.
- If a new owner-level policy is required, stop and report it instead of inventing it.

## Owner decisions

None required to begin.

## Completion report

### Implemented

- Added `advancore/agent_runner/controller_handoff.py` with a bounded local
  controller handoff request model (`ControllerHandoff`), explicit state model
  (`HandoffState`), deterministic reconciliation logic, and safe read/write
  helpers.
- Added `controller-handoff` CLI subcommand with `prepare`, `show`, and
  `reconcile` operations in `advancore/agent_runner/__main__.py`.
- Extended `advancore/agent_runner/audit.py` with
  `build_handoff_audit_payload()` and wrote `handoff_prepare` /
  `handoff_reconcile` audit records from the CLI.
- Exported the new public API through `advancore/agent_runner/__init__.py`.
- Added comprehensive tests in `tests/test_controller_handoff.py` covering
  request creation, validation failures, reconciliation, authority restrictions,
  idempotency/conflict protection, read-only inspection, audit behavior, CLI
  integration, and write-failure reporting.
- Updated `docs/architecture/AGENT_RUNNER.md` with the handoff request concept,
  flow diagram, safety model, CLI usage, and factual assertions.
- Added `docs/decisions/ADR-013-controller-handoff-queue.md` documenting the
  architectural decision, consequences, and alternatives considered.

### Files changed

- `advancore/agent_runner/controller_handoff.py` (new)
- `advancore/agent_runner/audit.py`
- `advancore/agent_runner/__main__.py`
- `advancore/agent_runner/__init__.py`
- `tests/test_controller_handoff.py` (new)
- `docs/architecture/AGENT_RUNNER.md`
- `docs/decisions/ADR-013-controller-handoff-queue.md` (new)
- `tasks/TASK-013-controller-handoff-queue-foundation.md`

### Database changes

None. No schema, model, migration, or production database change was made.

### Tests and results

```bash
.venv/bin/python -m pytest tests/ -v
```

Result: **240 passed** (includes 40 new controller-handoff tests).

Key coverage:
- Valid review bundle → `WAITING_DECISION` handoff request.
- Request contains correct task/bundle/branch/HEAD/recommendation metadata and
  excludes sensitive/full-content fields.
- Missing/malformed bundle, unsupported recommended action, and branch mismatch
  fail closed during prepare.
- Valid matching controller decision reconciles to `DECISION_RECEIVED`.
- Worker actor, task ID/filename mismatch, bundle reference mismatch, and
  missing/malformed decision record are rejected.
- Same-decision reconciliation is idempotent; different-decision reconciliation
  fails closed without overwriting.
- Read-only `show` does not mutate Git or artifact state.
- Prepare/reconcile do not mutate task files, Git publication state, or lifecycle
  state.
- Handoff prepare/reconcile produce local audit records.
- Handoff write failures are explicit.

### Assumptions

- The current `.agent_runner/` gitignore rule is sufficient for the new
  `controller_handoff/` subdirectory.
- Future transport/adapter tasks will reuse the request/decision linkage
  contract introduced here rather than redesigning governance.
- The existing `controller_decision` module remains the sole producer of valid
  decision records; tampered records are caught by validation.

### Risks / unresolved issues

- None identified. The implementation stays strictly within the local
  `.agent_runner/` scope and does not add network transport, automatic
  controller invocation, or lifecycle mutation.

### Decisions required

- None. The task was implemented within approved scope and existing policy.

### Recommended next step

- Review and approve this task.
- A future task may add a controller adapter or remote transport layer on top
  of the handoff request/decision linkage contract.
- Consider adding optional checksums or signing for tamper-evident handoff if
  the control-plane review surface expands.
