# TASK-048 — Authorized Unattended Orchestration Mode

STATUS: REVIEW

## Objective

Connect standing routine authority and fixed Kimi-first routing to the existing
resumable orchestrator through one explicit unattended mode.

## In scope

- Add an explicit checkpointed `unattended` orchestration option and CLI flag.
- Require the fixed Kimi-Swarm primary/Codex fallback route in that mode.
- Route launches through TASK-045/TASK-047 authority wrappers.
- Preserve existing checkpoints, repair limits, resume validation and manual
  task/implementation approval gates.
- Add focused tests and documentation.

## Out of scope

Inferring approval, automatically applying owner actions, merge, `main`,
deployment, credentials, destructive actions, daemons, or vendor dependencies.

## Allowed changed-file scope

- `tasks/TASK-048-authorized-unattended-orchestration-mode.md`
- `advancore/agent_runner/orchestration.py`
- `advancore/agent_runner/__main__.py`
- `tests/test_orchestration.py`
- `docs/runbooks/UNATTENDED_ORCHESTRATION.md`

## Owner decisions

None. The owner authorized unattended routine execution while leaving all
manual approval gates for their return.

## Completion report

### Implemented

- Added an explicit checkpointed `--unattended` mode.
- Fixed the mode to Kimi-Swarm primary and Codex fallback.
- Connected actual orchestration worker launches to controller-owned standing
  authority and the existing usage/integrity boundaries.
- Preserved manual approval, merge, `main`, deployment and credential gates.

### Files changed

- `tasks/TASK-048-authorized-unattended-orchestration-mode.md`
- `advancore/agent_runner/orchestration.py`
- `advancore/agent_runner/__main__.py`
- `tests/test_orchestration.py`
- `docs/runbooks/UNATTENDED_ORCHESTRATION.md`

### Database changes

None.

### Tests executed and results

- Focused orchestration/routing/authority suites: 81 passed.
- Python compile and `git diff --check`: passed.

### Decisions required

- Independent review and implementation approval remain manual.
