# TASK-011 — Controller Decision Record Foundation

STATUS: READY

## Objective

Create a standardized, machine-readable controller decision record that links an independent review decision to a specific review bundle without granting the worker any approval, commit, push, merge, deployment, or owner authority.

This task is the next handoff layer after TASK-010. The review bundle carries trusted runner evidence to the controller; the controller decision record must carry the controller's decision back into the local control plane in a bounded, auditable form.

## Business context

The current flow now provides:

`GitHub Task → Local Agent Runner → Kimi worker → tests → post-worker verification → audit → review bundle`

The remaining manual-courier gap is the return path from independent controller/reviewer review back into the runner/lifecycle system. Today that decision is communicated manually through terminal/chat instructions.

TASK-011 establishes a local decision artifact only. It must not automate Git publication or merge and must not let a worker approve its own work.

## Facts

- TASK-009 provides authority-aware lifecycle transitions.
- TASK-010 provides local review bundles under `.agent_runner/review/`.
- Review bundles may recommend only `REVIEW`, `REWORK`, or `BLOCKED`; they never recommend `APPROVED`.
- Lifecycle approval authority belongs to controller/reviewer or owner, never worker.
- Commit, push, merge, deployment, destructive actions, secrets access, and commercial/compliance changes remain separately gated.

## In scope

1. Add a controller-decision model and serializer under `advancore/agent_runner/`.
2. Store local decision records under `.agent_runner/decisions/`, covered by the existing `.agent_runner/` gitignore rule.
3. Use deterministic machine-readable JSON.
4. A decision record must link to one existing review bundle and include only bounded safe metadata, including:
   - timestamp,
   - task ID and task filename,
   - review-bundle path/reference,
   - review-bundle task identity,
   - review-bundle branch,
   - review-bundle pre/post HEAD when available,
   - controller decision,
   - bounded rationale/notes,
   - actor role,
   - decision-record version.
5. Allowed controller decisions are exactly:
   - `APPROVE` — independent controller accepts the implementation for the next human-gated publication step;
   - `REWORK` — implementation requires further worker changes;
   - `BLOCKED` — review cannot proceed safely or required evidence/decision is missing.
6. `APPROVE` is a controller decision record value only. It must not itself perform a Git commit, push, merge, deployment, or task transition.
7. Reject any attempt to create a decision record with actor role `worker`.
8. Reject unknown decision values and malformed/missing review bundles.
9. Validate that task identity in the decision request matches the linked review bundle.
10. Validate branch/HEAD evidence from the linked bundle and fail closed when the linkage is inconsistent or ambiguous.
11. Add CLI support with safe defaults, for example:
    - `controller-decision record <bundle-or-latest> --decision APPROVE|REWORK|BLOCKED --actor controller --note "..."`
    - `controller-decision show <path-or-latest>`
12. Recording a decision must be explicit; inspection must be read-only.
13. The CLI must clearly print the resulting local decision-record path.
14. Decision records must never contain:
    - credentials or secrets,
    - environment dumps,
    - connection strings,
    - full task bodies,
    - full worker transcripts,
    - arbitrary command output,
    - customer/business operational data.
15. Add audit metadata for decision-record creation using the existing local audit architecture or a small compatible extension.
16. Add deterministic tests for serialization, validation, actor restrictions, review-bundle linkage, safe-field policy, inspection, write failure, and audit behavior.
17. Update `docs/architecture/AGENT_RUNNER.md` and add an ADR if appropriate.
18. Run the full pytest suite.
19. Complete the task-file Completion report and stop without committing or pushing.

## Out of scope

- Automatic Git staging.
- Automatic commit or push.
- Merge or branch switching.
- GitHub write actions from the runner.
- Automatic deployment.
- Automatic task transition to `APPROVED`.
- Automatic invocation of the controller.
- Network transport of bundles or decisions.
- Cryptographic identity/signatures.
- Replacing the existing lifecycle authority model.
- Giving controller or owner authority to Kimi/worker.
- Database/model/migration changes.
- ERP/business feature work.
- General orchestration redesign.

## Database impact

None. No schema, model, migration, or production database change is authorised.

## Safety requirements

- Stay on `agent-control-foundation`.
- `main` remains non-executable and untouched.
- Existing pre/post Git safety checks remain unchanged.
- Worker must never be accepted as a controller decision actor.
- Controller decision recording must not imply owner authority.
- An `APPROVE` decision record must not perform or imply commit/push/merge/deployment.
- Decision artifacts remain repository-local under `.agent_runner/decisions/` and gitignored.
- Decision construction must trust the linked review bundle and runner-derived evidence, not worker-authored approval claims.
- Unknown, missing, conflicting, or malformed evidence must fail closed.

## Acceptance criteria

- [ ] A valid controller decision can be recorded locally against an existing review bundle.
- [ ] Decision values are limited to `APPROVE`, `REWORK`, or `BLOCKED`.
- [ ] Actor role `worker` cannot create a controller decision record.
- [ ] Decision record links unambiguously to its review bundle and task identity.
- [ ] Mismatched task/bundle identity is rejected.
- [ ] Malformed or missing review bundle is rejected.
- [ ] Decision record contains only safe bounded metadata.
- [ ] Decision record excludes prohibited/sensitive/full-content fields.
- [ ] CLI prints the decision-record path clearly.
- [ ] Read-only decision inspection works and does not mutate Git state.
- [ ] Decision-record write failure is explicit and tested.
- [ ] Decision creation is auditable locally.
- [ ] `APPROVE` does not stage, commit, push, merge, deploy, or transition the task automatically.
- [ ] No commit/push/merge capability is added to the runner.
- [ ] No task authority expansion is added for workers.
- [ ] No database/model/migration changes are made.
- [ ] Full pytest suite passes.
- [ ] Architecture documentation is updated.
- [ ] Completion report is written into this task file.

## Test requirements

At minimum test:

1. Controller + valid review bundle + `APPROVE` -> local decision record created.
2. Controller + valid review bundle + `REWORK` -> local decision record created.
3. Controller + valid review bundle + `BLOCKED` -> local decision record created.
4. Worker actor -> rejected for all controller decision values.
5. Unknown decision value -> rejected.
6. Missing review bundle -> rejected.
7. Malformed review bundle -> rejected.
8. Task identity mismatch -> rejected.
9. Safe metadata fields are present.
10. Secrets/full task/full transcript/arbitrary output are absent.
11. Decision write failure is reported explicitly.
12. Audit reference/record is produced when available.
13. Read-only inspection does not alter Git state.
14. `APPROVE` does not mutate Git, task lifecycle state, or remote state.
15. Existing runner, review-bundle, lifecycle, audit, and non-runner tests remain passing.

Run:

```bash
.venv/bin/python -m pytest tests/ -v
```

## Constraints

- Read and obey `AGENTS.md`.
- Inspect existing TASK-009 lifecycle and TASK-010 review-bundle implementations before coding.
- Stay on `agent-control-foundation`.
- Do not modify `main`.
- Do not commit or push until explicit reviewer approval.
- Keep changes small and reversible.
- Prefer standard-library JSON/path/time support over new dependencies.
- Do not introduce network services or new external dependencies unless absolutely required; if required, stop and report instead.

## Owner decisions

None required to begin.

## Completion report

### Implemented

- Added `advancore/agent_runner/controller_decision.py` with `DecisionValue`,
  `ControllerDecision`, `ControllerDecisionError`, `ControllerDecisionWriteError`,
  deterministic serialization, validation, writing/loading/inspection helpers.
- Extended `advancore/agent_runner/audit.py` with
  `build_controller_decision_audit_payload()` for decision audit metadata.
- Updated `advancore/agent_runner/__init__.py` to export the new public symbols.
- Added `controller-decision record|show` CLI to
  `advancore/agent_runner/__main__.py` with explicit success/failure output and
  audit integration.
- Added `tests/test_controller_decision.py` covering all TASK-011 test
  requirements.
- Added `docs/decisions/ADR-007-controller-decision-record.md`.
- Updated `docs/architecture/AGENT_RUNNER.md` with the new module, flow,
  safety-model principle, CLI usage, threat boundaries, and facts.

### Files changed

- `advancore/agent_runner/__init__.py`
- `advancore/agent_runner/__main__.py`
- `advancore/agent_runner/audit.py`
- `advancore/agent_runner/controller_decision.py` (new)
- `docs/architecture/AGENT_RUNNER.md`
- `docs/decisions/ADR-007-controller-decision-record.md` (new)
- `tasks/TASK-011-controller-decision-record-foundation.md`
- `tests/test_controller_decision.py` (new)

### Database changes

None. No schema, model, migration, or production database changes were made.

### Tests and results

```bash
.venv/bin/python -m pytest tests/ -v
```

Result: **170 passed in 2.64s**.

### Assumptions

- The controller decision record remains a local artifact under
  `.agent_runner/decisions/`; future tasks will define any cross-machine or
  signed transport if required.
- `owner` may record controller decisions because owner authority already
  subsumes controller/reviewer authority in the lifecycle model.

### Risks / unresolved issues

- Decision records are not cryptographically signed; tamper-evidence is not yet
  implemented.
- The CLI does not invoke the controller automatically; human controller input
  is still required.

### Decisions required

None at this time.

### Recommended next step

Review this task and, once approved, the controller may transition TASK-011 to
`APPROVED` through the existing `transition` command and proceed to the next
approved task.

### git status --short

```
 M advancore/agent_runner/__init__.py
 M advancore/agent_runner/__main__.py
 M advancore/agent_runner/audit.py
 M docs/architecture/AGENT_RUNNER.md
?? advancore/agent_runner/controller_decision.py
?? docs/decisions/ADR-007-controller-decision-record.md
?? tests/test_controller_decision.py
```
