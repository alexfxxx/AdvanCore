# TASK-025 — Explicit Owner Decision Intake and One-Command Resume

STATUS: APPROVED

## Objective

Remove the remaining command-and-artifact courier step at orchestration approval
gates by allowing one explicit, phase-bound owner action to be recorded and the
same run resumed through existing governance APIs, without inferring approval
or granting authority to a worker or local execution client.

## Business context

TASK-021 coordinates the complete governed loop and pauses at task approval and
implementation review. TASK-022 through TASK-024 make worker execution
provider-resilient and bounded. Today, after the owner says “approve,” a local
operator must still discover task/bundle identifiers, invoke separate lifecycle
or controller-decision commands, and then invoke orchestration resume.

Codex desktop can translate a clearly expressed owner decision into a local CLI
invocation, but permanent AdvanCore code must validate and record that authority.
The owner should provide the decision; the operator should not become the
decision-maker merely by relaying it.

## In scope

1. Add an explicit orchestration-resume option equivalent to `--owner-action`
   with a fixed code-owned enum:
   - `APPROVE_TASK`;
   - `BLOCK_TASK`;
   - `APPROVE_IMPLEMENTATION`;
   - `REWORK_IMPLEMENTATION`;
   - `BLOCK_IMPLEMENTATION`.
2. Accept owner action only with `--resume <run-id>`. Reject it for a new goal,
   without a run ID, or when mixed with conflicting adapter/budget changes.
3. Preview remains the default. Preview must validate the checkpoint, phase,
   task/bundle linkage, Git branch/HEAD, and intended existing API calls while
   writing no decision, lifecycle, checkpoint, Git, or publication state.
4. Apply an action only at its exact matching gate:
   - task actions only at `AWAITING_TASK_APPROVAL` and against the checkpointed
     DRAFT task;
   - implementation actions only at `AWAITING_IMPLEMENTATION_DECISION` and
     against the checkpointed, current review bundle and handoff evidence.
5. `APPROVE_TASK` must reuse the existing owner/controller lifecycle transition
   for `DRAFT -> READY`; it must not edit task status directly.
6. Implementation actions must build and durably write the existing TASK-011
   `ControllerDecision` record with actor `owner`, exact task/bundle linkage,
   current branch/HEAD evidence, and an optional bounded single-line note.
7. After a successful action record, continue the same orchestration invocation
   through its existing resume state machine. Do not duplicate reconciliation,
   lifecycle bridge, rework, finalization, staging, commit, or push logic.
8. Make action intake idempotent: an already-recorded exactly matching action
   may be reconciled safely; conflicting, duplicate-ambiguous, stale, consumed,
   or phase-mismatched actions fail closed.
9. Never default a missing action to approval, infer an action from natural
   language, tests, worker output, task content, exit status, or checkpoint data.
10. Persist bounded owner-action evidence in the orchestration checkpoint and
    consolidated report: action, actor, linked evidence path, applied/preview
    state, and one next action. Do not persist conversation transcripts.
11. Ensure Codex, Kimi, Kimi-Swarm, controller adapters, and transport drivers
    cannot supply `--owner-action` from worker output or gain owner authority.
12. Document the permanent/local split: AdvanCore validates and records explicit
    authority; Codex desktop or another approved client may invoke the command
    only after the owner actually provides the decision.

## Out of scope

- Automatic or inferred owner/controller approval.
- Natural-language decision parsing inside AdvanCore.
- Authentication, identity federation, remote APIs, webhooks, daemons, or GUIs.
- Changing controller-decision or lifecycle schemas.
- Worker self-review or self-approval.
- Merge, deployment, releases, tags, `main`, or credentials.

## Allowed changed-file scope

1. `advancore/agent_runner/orchestration.py`
2. `advancore/agent_runner/__main__.py`
3. `advancore/agent_runner/__init__.py`
4. `tests/test_owner_decision_intake.py` (new)
5. `docs/architecture/AGENT_RUNNER.md`
6. `docs/runbooks/OWNER_DECISION_RESUME.md` (new)
7. `docs/decisions/ADR-025-explicit-owner-decision-intake-resume.md` (new)
8. `tasks/TASK-025-explicit-owner-decision-intake-resume.md`

No other file may change.

## Acceptance criteria

1. Fixed owner actions are accepted only on explicit resume at their matching gate.
2. Preview writes nothing and shows exact intended authority and continuation.
3. Task approval uses the existing lifecycle API and resumes execution.
4. Implementation actions use the existing decision record/reconciliation path.
5. APPROVE can reach existing TASK-020 finalization only after all existing gates.
6. REWORK and BLOCKED retain existing bounded behavior.
7. Missing, invalid, stale, conflicting, or worker-supplied decisions fail closed.
8. Resume cannot silently change checkpointed providers, budgets, or timeout.
9. Reports/artifacts remain bounded and contain no transcripts or credentials.
10. Full repository test suite passes and exactly eight approved paths change.

## Required verification

```bash
.venv/bin/python -m pytest tests/test_owner_decision_intake.py -v
.venv/bin/python -m pytest tests/ -v
git diff --check
```

## Owner decisions

The owner approved proceeding to the next task on `agent-control-foundation`.
TASK-025 implements a mechanism for future explicit decisions; this instruction
does not pre-approve TASK-025 implementation or authorize inferred decisions.

## Completion report

### Implemented

- Added fixed, resume-only owner actions for task approval/blocking and
  implementation approval/rework/blocking.
- Added fail-closed phase, task/bundle/handoff, branch/HEAD, note, duplicate,
  conflict, and resume-override validation.
- Added write-free preview and explicit apply paths that reuse lifecycle,
  controller-decision, handoff reconciliation, and orchestration APIs.
- Added bounded owner-action evidence to checkpoints and consolidated reports.
- Added focused tests, architecture documentation, operator runbook, and ADR.

### Files changed

- `advancore/agent_runner/orchestration.py`
- `advancore/agent_runner/__main__.py`
- `advancore/agent_runner/__init__.py`
- `tests/test_owner_decision_intake.py`
- `docs/architecture/AGENT_RUNNER.md`
- `docs/runbooks/OWNER_DECISION_RESUME.md`
- `docs/decisions/ADR-025-explicit-owner-decision-intake-resume.md`
- `tasks/TASK-025-explicit-owner-decision-intake-resume.md`

### Database changes

- None.

### Tests and results

- `.venv/bin/python -m pytest tests/test_owner_decision_intake.py -v` — 10 passed.
- `.venv/bin/python -m pytest tests/ -v` — 590 passed.
- `git diff --check` — passed.

### Assumptions

- The optional owner note is bounded to one line and 400 characters, stricter
  than the existing generic controller-decision field bound.
- An approved local client supplies the fixed enum only after the owner has
  explicitly made the decision; AdvanCore does not parse natural language.

### Risks / unresolved issues

- Authentication, identity federation, and remote decision intake remain out
  of scope; the command relies on the approved local operating boundary.
- Final owner/controller review is still required before any commit or status
  transition of this task.

### Decisions required

- Owner/controller review of the TASK-025 implementation and evidence.
- No DRAFT-to-READY or implementation approval decision was made by the worker.

### Recommended next step

- Review the eight scoped file changes and verification evidence, then record
  the owner/controller decision through the existing governed process.
