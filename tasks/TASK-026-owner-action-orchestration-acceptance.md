# TASK-026 — Owner-Action Orchestration Acceptance

STATUS: READY

## Objective

Validate the complete TASK-025 owner-action resume path across both approval
gates and existing finalization delegation using deterministic end-to-end tests,
and repair only defects exposed by that validation.

## Business context

TASK-025 removes separate lifecycle/decision courier commands. Before treating
the owner loop as operationally complete, AdvanCore needs one acceptance suite
that follows a single correlated orchestration run from a DRAFT task through
explicit owner task approval, verified implementation evidence, explicit owner
implementation decision, and delegation to TASK-020 finalization.

The suite must use temporary repositories and controlled local fakes rather than
live AI providers or GitHub. It must exercise production orchestration, lifecycle,
decision, handoff, checkpoint, resume, and report code wherever practical.

## In scope

1. Add deterministic acceptance tests for one correlated orchestration run:
   - pause at `AWAITING_TASK_APPROVAL`;
   - preview and apply `APPROVE_TASK`;
   - continue to task execution and pause at implementation review;
   - preview and apply `APPROVE_IMPLEMENTATION`;
   - reconcile the owner decision and delegate to existing finalization;
   - reach only the controlled fake `PUSHED` terminal result.
2. Prove preview at both gates writes no lifecycle, decision, handoff, checkpoint,
   Git, or publication state.
3. Prove exact task, run, bundle, branch, and HEAD correlation across resumes.
4. Prove stale HEAD, wrong phase, conflicting action, consumed evidence, and
   resume-time configuration overrides stop before mutation/finalization.
5. Prove a worker cannot create or inject owner-action evidence.
6. Prove repeated resume after the controlled terminal result is idempotent and
   does not repeat finalization.
7. Repair orchestration/CLI code only when an acceptance test exposes a defect;
   do not broaden the interface or create new authority.
8. Update the owner decision runbook and architecture acceptance evidence.

## Out of scope

- Live provider, GitHub, network, credential, merge, deployment, release, or `main` operations.
- New owner actions, controller schemas, lifecycle states, adapters, or transports.
- Automatic/inferred approval or natural-language parsing.
- Production publication during tests.

## Allowed changed-file scope

1. `advancore/agent_runner/orchestration.py`
2. `advancore/agent_runner/__main__.py`
3. `tests/test_owner_action_orchestration_e2e.py` (new)
4. `docs/architecture/AGENT_RUNNER.md`
5. `docs/runbooks/OWNER_DECISION_RESUME.md`
6. `docs/decisions/ADR-026-owner-action-orchestration-acceptance.md` (new)
7. `tasks/TASK-026-owner-action-orchestration-acceptance.md`

No other file may change. Production modules should remain unchanged if the
acceptance suite finds no defect.

## Acceptance criteria

1. Both owner-action gates are exercised through production resume logic.
2. Existing lifecycle, controller-decision, handoff, and finalization APIs are used.
3. Preview is demonstrably side-effect free at both gates.
4. Correlation, stale evidence, conflicts, consumed evidence, and override gates fail closed.
5. Terminal resume is idempotent and finalization occurs at most once.
6. No live provider/network/publication dependency exists in tests.
7. Full repository test suite passes.
8. Exact changed paths remain within the seven approved paths.

## Required verification

```bash
.venv/bin/python -m pytest tests/test_owner_action_orchestration_e2e.py -v
.venv/bin/python -m pytest tests/ -v
git diff --check
```

## Owner decisions

The owner authorized continued work for the next bounded tasks while remaining
available by phone. This authorizes TASK-026 preparation and execution but does
not convert blanket authorization into an inferred evidence-specific approval.

## Completion report

### Implemented

### Files changed

### Database changes

### Tests and results

### Assumptions

### Risks / unresolved issues

### Decisions required

### Recommended next step
