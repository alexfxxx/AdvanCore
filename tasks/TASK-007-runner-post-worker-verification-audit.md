# TASK-007 — Runner Post-Worker Verification and Audit Hardening

STATUS: READY

## Objective

Harden the Local Agent Runner after TASK-006 by independently verifying repository state after the worker exits, making the approval gate explicit, and writing a durable local audit record for each runner invocation.

This task improves verification and observability only. It does not grant the runner authority to commit, push, merge, deploy, change task status, or broaden business scope.

## Context

TASK-006 proved:

`GitHub READY task -> Local Agent Runner -> Kimi -> implementation/tests -> human/reviewer gate`

It also exposed three gaps:

1. Post-worker Git state was not captured as a first-class verification result.
2. Final `AWAITING_APPROVAL` status was not obvious enough in terminal output.
3. Runner invocations had no durable audit record outside terminal history.

## In scope

1. Capture a pre-worker Git snapshot containing repository root, current branch, HEAD SHA, and working-tree state.
2. Capture a post-worker Git snapshot immediately after the worker exits.
3. Verify that:
   - branch is unchanged,
   - branch is not `main`,
   - HEAD SHA is unchanged,
   - worker-created uncommitted changes are surfaced clearly.
4. If branch or HEAD changes unexpectedly, do not return `AWAITING_APPROVAL`.
5. Keep worker success/failure separate from repository-safety verification.
6. Make successful execution visibly end with:
   - `Result status: awaiting_approval`
   - `Post-worker verification: PASS`
   - changed-path summary
   - reminder that commit/push remain gated.
7. Add a durable local audit record for plan and execute invocations under `.agent_runner/audit/`.
8. Add `.agent_runner/` to `.gitignore`.
9. Use a simple machine-readable format such as JSON Lines or one JSON object per invocation.
10. Audit only safe metadata, including:
    - timestamp,
    - task ID and filename,
    - mode,
    - worker type,
    - branch,
    - pre/post HEAD,
    - validation result,
    - worker result,
    - post-worker verification result,
    - final runner status,
    - changed paths when applicable.
11. Do not store environment dumps, credentials, connection strings, full task bodies, full worker transcripts, or business/customer data.
12. Report audit-write failure explicitly instead of silently ignoring it.
13. Add deterministic tests for verification and audit behavior.
14. Run the full pytest suite.
15. Update `docs/architecture/AGENT_RUNNER.md` and add/update an ADR if appropriate.
16. Complete this task report and stop without committing or pushing.

## Out of scope

- Automatic staging, commit, push, merge, or branch switching.
- Remote synchronization.
- GitHub write actions from the runner.
- Database or ERP feature work.
- Task-status mutation.
- General command execution sourced from task-file content.
- Multi-turn/long-running session orchestration.
- Broad Agent Runner redesign.

## Database impact

None.

## Safety requirements

- Fail closed on unexpected branch movement.
- Fail closed on unexpected HEAD movement.
- Do not infer repository safety only from worker exit code.
- Post-worker verification must come from the runner's own Git inspection.
- Existing dry-run behavior remains default.
- Kimi execution remains explicitly opt-in.
- `main` remains non-executable.
- Commit/push/merge remain reviewer gated.

## Acceptance criteria

- [ ] Pre-worker snapshot includes branch and HEAD SHA.
- [ ] Post-worker snapshot is captured.
- [ ] Unexpected HEAD movement blocks approval.
- [ ] Unexpected branch movement blocks approval.
- [ ] Worker success cannot override failed repository verification.
- [ ] Successful execution clearly displays `AWAITING_APPROVAL` or equivalent.
- [ ] Changed paths are surfaced after worker execution.
- [ ] Local audit records are created for plan and execute invocations.
- [ ] Audit records contain only approved safe metadata.
- [ ] Audit runtime directory is gitignored.
- [ ] Audit-write failure is reported explicitly.
- [ ] No commit/push/merge capability is added.
- [ ] No database changes are made.
- [ ] Full pytest suite passes.
- [ ] Architecture documentation is updated.
- [ ] Completion report is produced.

## Test requirements

At minimum test:

1. Normal worker completion with unchanged branch/HEAD and visible changed files -> `AWAITING_APPROVAL`.
2. Unexpected HEAD movement -> blocked/failed approval state.
3. Unexpected branch movement -> blocked/failed approval state.
4. Worker failure remains distinct from Git verification result.
5. Audit record creation for plan and execute invocations.
6. Required safe audit fields and absence of sensitive/full-content fields.
7. Audit-write failure handling.
8. Existing runner and non-runner tests remain passing.

Run:

```bash
.venv/bin/python -m pytest tests/ -v
```

## Constraints

- Read and obey `AGENTS.md`.
- Stay on `agent-control-foundation`.
- Do not modify `main`.
- Do not commit or push until explicit reviewer approval.
- Keep changes small and reversible.
- Prefer standard-library JSON/path/time support over new dependencies.

## Owner decisions

None required to begin.

## Completion report

### Implemented

### Files changed

### Database changes

### Tests and results

### Assumptions

### Risks / unresolved issues

### Decisions required

### Recommended next step

### `git status --short`
