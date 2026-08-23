# ADR-026 — Owner-Action Orchestration Acceptance

STATUS: ACCEPTED

## Context

TASK-025 introduced explicit owner actions at the task-approval and
implementation-decision gates. The individual APIs were tested, but operational
acceptance required one correlated run through both gates and TASK-020
finalization delegation without live providers or publication.

## Decision

Maintain a deterministic temporary-repository acceptance suite that exercises
production orchestration, lifecycle, controller-decision, handoff, checkpoint,
resume, and result-report behavior. Replace only external planning/worker Git
facts and final publication with controlled local fakes. The only successful
terminal publication signal in this suite is the fake `PUSHED` result.

Owner-decision evidence is bound to the current task and review bundle. Any
matching evidence already recorded in `consumed_decision_paths` fails closed;
the orchestrator must not create replacement authority evidence for that bundle.

## Consequences

- Preview at either owner gate is verified byte-for-byte side-effect free.
- Task, run, bundle, handoff, branch, and HEAD correlation is covered across
  resumes.
- Wrong phase, stale HEAD, conflicting or worker-authored decisions, consumed
  evidence, and resume configuration changes stop before mutation/finalization.
- Repeated terminal resume is idempotent and delegates finalization at most once.
- The acceptance suite performs no network, credential, GitHub, production, or
  real publication operation.

## Verification

- `.venv/bin/python -m pytest tests/test_owner_action_orchestration_e2e.py -v`
- `.venv/bin/python -m pytest tests/ -v`
- `git diff --check`
