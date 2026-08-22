# TASK-007 — Runner Post-Worker Verification and Audit Hardening

STATUS: COMPLETE

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

- Added `head_sha` to `GitInfo` and captured it via `git rev-parse HEAD`.
- Introduced `PostWorkerVerification` in `runner.py` to compare pre- and post-worker Git snapshots.
- Added independent verification that branch is unchanged, branch is not `main`, and HEAD SHA is unchanged after the worker exits.
- Kept worker success/failure separate from repository-safety verification; worker success cannot override a failed verification.
- Added `POST_WORKER_VERIFICATION_FAILED` runner status.
- Created `advancore/agent_runner/audit.py` for durable JSON Lines audit records under `.agent_runner/audit/runner.jsonl`.
- Both `plan()` and `execute()` now write a local audit record with safe metadata only.
- Audit-write failures are reported explicitly without silently masking the runner's primary status.
- Updated CLI output to show HEAD, post-worker verification result, changed paths, audit path, and a clear `awaiting_approval` status.
- Added `.agent_runner/` to `.gitignore`.
- Updated `docs/architecture/AGENT_RUNNER.md`.
- Added `docs/decisions/ADR-004-runner-post-worker-verification-audit.md`.

### Files changed

- `.gitignore`
- `advancore/agent_runner/__init__.py`
- `advancore/agent_runner/__main__.py`
- `advancore/agent_runner/audit.py` (new)
- `advancore/agent_runner/git_info.py`
- `advancore/agent_runner/runner.py`
- `docs/architecture/AGENT_RUNNER.md`
- `docs/decisions/ADR-004-runner-post-worker-verification-audit.md` (new)
- `tests/test_agent_runner.py`
- `tasks/TASK-007-runner-post-worker-verification-audit.md`

### Database changes

None.

### Tests and results

- Added `TestPostWorkerVerification` covering unchanged state, HEAD movement, branch movement, post-worker `main`, and changed-path surfacing.
- Added `TestRunnerPostWorkerVerification` covering end-to-end `AWAITING_APPROVAL`, blocked approval on HEAD/branch movement, and distinct handling of worker vs verification failure.
- Added `TestAuditRecords` covering audit creation for `plan` and `execute`, safe field coverage, exclusion of sensitive content, and explicit audit-write failure reporting.
- Updated existing tests for the new `GitInfo` field and audit behaviour.
- Full suite: `77 passed`.

### Assumptions

- `git status --porcelain` lines use standard two-character status codes followed by a space, so changed paths are extracted from index 3 onward.
- Audit records are stored locally in JSON Lines format; a remote or database-backed audit store is out of scope.
- Audit-write failure is reported but does not change the runner's primary status.

### Risks / unresolved issues

- A worker could still create untracked files or make working-tree changes; the runner surfaces these but does not auto-clean or stash them.
- Audit records are local and not tamper-evident; future work may add integrity protections if required.
- The runner does not detect all possible repository mutations (e.g., tags, refs, staged changes that preserve HEAD); the current checks cover branch and HEAD movement, which are the highest-risk cases.

### Decisions required

None.

### Recommended next step

- Review the changes, then approve commit/push separately.
- Consider a future task to surface the audit log via a CLI `audit` or `status` subcommand.

### `git status --short`

```
 M .gitignore
 M advancore/agent_runner/__init__.py
 M advancore/agent_runner/__main__.py
 M advancore/agent_runner/git_info.py
 M advancore/agent_runner/runner.py
 M docs/architecture/AGENT_RUNNER.md
 M tests/test_agent_runner.py
?? advancore/agent_runner/audit.py
?? docs/decisions/ADR-004-runner-post-worker-verification-audit.md
```
