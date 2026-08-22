# TASK-008 — Runner Audit Runtime Validation

STATUS: READY

## Objective

Prove the installed TASK-007 runner behavior in a real supervised execution without modifying runner implementation code.

## Context

TASK-007 added post-worker Git verification, explicit approval-gate output, changed-path reporting, and local JSONL audit records. Because TASK-007 modified the runner while the previous runner process was already running, those new behaviors need one fresh execution to validate them at runtime.

## In scope

1. Create `docs/validation/RUNNER_AUDIT_RUNTIME.md`.
2. Record that this task exists solely to validate the newly installed runner behavior.
3. Add `tests/test_runner_audit_runtime_artifact.py` with deterministic checks that the validation document exists and contains these headings:
   - Purpose
   - Expected runner behavior
   - Validation result
   - Safety observations
   - Recommended next step
4. Run the full pytest suite.
5. Complete this task report.
6. Stop with completion report and git status.

## Out of scope

- Changes to `advancore/agent_runner/`.
- Database, migration, ERP, deployment, or production changes.
- Commit, push, merge, or branch switching by the worker.
- Secret or credential access.
- Broader orchestration redesign.

## Acceptance criteria

- Validation document exists.
- Artifact test exists and passes.
- Full pytest suite passes.
- No Agent Runner implementation files change.
- No database/model/migration files change.
- Worker does not commit or push.
- Outer runner reports `awaiting_approval` after worker completion.
- Outer runner reports post-worker verification PASS.
- Outer runner surfaces changed paths.
- `.agent_runner/audit/runner.jsonl` exists after execution and contains a TASK-008 execute record.

## Database impact

None.

## Test requirements

Run:

```bash
.venv/bin/python -m pytest tests/ -v
```

## Constraints

- Read and obey `AGENTS.md`.
- Stay on `agent-control-foundation`.
- Do not modify `main`.
- Do not commit or push.

## Completion report

Report:
- Implemented
- Files changed
- Database changes
- Tests and results
- Assumptions
- Risks / unresolved issues
- Decisions required
- Recommended next step
- `git status --short`
