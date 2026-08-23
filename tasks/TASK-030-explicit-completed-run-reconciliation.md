# TASK-030 — Explicit completed-run reconciliation

STATUS: APPROVED

## Objective

Provide an explicit fail-closed runner command that reconciles a stale orchestration checkpoint to its existing terminal outcome only when authoritative task, branch, remote synchronization, controller-decision, and successful-finalization evidence all match.

## Business context

A finalization may complete successfully while its orchestration checkpoint remains stale because the runner did not persist the terminal state. Operators need a narrowly bounded recovery path that recognizes already-completed work without reconstructing authority, repeating publication, or weakening the normal stale-evidence protections.

## Facts

- AGENTS.md makes GitHub the source of truth for code and approved knowledge.
- The existing agent_runner stores resumable orchestration checkpoints under .agent_runner/orchestration.
- The existing finalization boundary validates controller decisions and records finalization evidence.
- The existing orchestration flow treats stale evidence as a fail-closed condition.
- The requested capability is an explicit reconciliation command, not an automatic orchestration recovery.
- Reconciliation must require the same task to have lifecycle state APPROVED.
- Reconciliation must require a named non-main current branch matching the checkpoint.
- Reconciliation must require synchronized local and origin tips for that branch.
- Reconciliation must require matching controller-decision evidence and successful finalization evidence.
- All pre-existing and newly generated evidence must be preserved.

## Assumptions

- A successful existing finalization artifact contains sufficient task, decision, branch, commit, and outcome identity to bind it deterministically to one orchestration checkpoint.
- The origin tracking reference can be inspected locally without fetching, accessing credentials, or contacting a remote.
- The terminal checkpoint outcome should reflect the already-recorded successful finalization outcome and must not initiate another finalization or publication attempt.
- The reconciliation audit can be represented as bounded append-only evidence plus an atomic checkpoint update without introducing a new architectural subsystem.

## In scope

- Add one explicitly invoked agent_runner CLI command for completed-run reconciliation.
- Resolve exactly one caller-supplied orchestration run and fail closed when its checkpoint cannot be loaded or is not eligible for reconciliation.
- Require the checkpoint task to resolve to the same repository task and require its current lifecycle state to be APPROVED.
- Require a named current branch that is not main and exactly matches the checkpoint branch.
- Require the current local branch tip and corresponding local origin tracking reference to identify the same finalized commit.
- Resolve exactly one existing controller decision from the canonical decision evidence directory with an allowed owner or controller actor, APPROVE value, and exact linkage to the checkpoint's task and review bundle; validate a checkpoint decision reference when one was persisted, but do not require it after an interrupted handoff.
- Resolve exactly one successful finalization record from the canonical append-only finalization artifact matching the same task, decision, review evidence, branch, review HEAD as its pre-commit HEAD, and synchronized finalized commit; validate a checkpoint finalization reference when one was persisted, but do not require it after an interrupted handoff.
- Reject missing, malformed, ambiguous, duplicated, conflicting, stale, or mismatched evidence.
- Record bounded reconciliation evidence and atomically update only the eligible orchestration checkpoint to its already-proven terminal outcome.
- Preserve all task, checkpoint, controller, review, audit, and finalization evidence.
- Add concise deterministic unit and CLI tests using isolated temporary repositories and local Git references.
- Update only the runner documentation needed to describe eligibility, invocation, evidence, and fail-closed behavior.

## Explicitly out of scope

- Automatic reconciliation during ordinary orchestration or stale-evidence handling.
- Inferring approval from worker success, verification success, a checkpoint value, Git state, or finalization output.
- Creating, modifying, replacing, or auto-approving a controller decision.
- Running or repeating finalization, staging files, committing, pushing, fetching, merging, tagging, releasing, or deploying.
- Switching branches or changing HEAD, main, remotes, tracking configuration, the index, or working-tree content.
- Resetting, rebasing, force-pushing, rewriting history, or repairing diverged branches.
- Relaxing, bypassing, or reinterpreting any ordinary stale-evidence validation.
- Reconciling detached HEAD, main, a branch without an origin tracking reference, diverged tips, or a checkpoint bound to another branch or commit.
- Deleting, truncating, replacing, or rewriting existing evidence artifacts.
- Credential, secret, token, network, production-data, database-schema, migration, commercial-rule, or compliance-rule changes.
- Broad orchestration, lifecycle, controller, audit, or finalization redesign.

## Allowed changed-file scope

- `advancore/agent_runner/orchestration.py`
- `advancore/agent_runner/__main__.py`
- `tests/test_orchestration.py`
- `tests/test_agent_runner.py`
- `docs/architecture/AGENT_RUNNER.md`
- `tasks/TASK-030-explicit-completed-run-reconciliation.md`

## Database impact

None

## Safety requirements

- GitHub remains the source-of-truth.
- `main` remains untouched and non-executable unless explicitly approved.
- Worker/swarm cannot approve its own work.
- No automatic staging, commit, push, merge, tag, deploy, switch, reset,
  rebase, or history rewrite.
- This generated task is DRAFT and cannot execute until a valid
  `DRAFT -> READY` controller/owner transition.
- Unknown, unsafe, malformed, conflicting, or ambiguous states fail closed.
- The planner proposed only; the runner constructed this DRAFT; the
  controller/owner must authorize execution.

## Acceptance criteria

- The CLI exposes a distinct explicitly invoked completed-run reconciliation command requiring one exact run identifier.
- The command performs no mutation until every eligibility and evidence check succeeds.
- Reconciliation succeeds only when the resolved task is currently APPROVED and matches the checkpoint task identity and path.
- Reconciliation succeeds only on a named non-main current branch that exactly matches the checkpoint branch.
- Reconciliation succeeds only when the current local branch tip, local origin tracking tip, and finalization post/commit evidence are identical, while the finalization pre-commit HEAD matches the checkpoint review bundle. A stale checkpoint's earlier expected HEAD is preserved as reconciliation evidence rather than incorrectly treated as the published commit.
- Reconciliation does not fetch or otherwise contact origin to establish synchronization.
- Exactly one valid APPROVE controller decision is resolved and proven to match the task and review evidence referenced by the checkpoint and finalization record.
- Exactly one successful finalization record is resolved and proven to match the task, decision, review evidence, branch, and finalized commit.
- A successful command records deterministic reconciliation evidence and marks the checkpoint with the terminal outcome already proven by finalization without rerunning finalization or publication.
- Existing checkpoint history, messages, consumed-decision references, controller decisions, review artifacts, finalization artifacts, and audit records remain available and unmodified except for the narrowly required atomic checkpoint transition and appended reconciliation evidence.
- Missing origin tracking state, absent refs, diverged tips, main, detached HEAD, task-state mismatch, branch mismatch, commit mismatch, non-APPROVE or unauthorized decisions, unsuccessful finalization, ambiguous matches, malformed evidence, and already-conflicting terminal state all fail closed with a non-zero result.
- A failed reconciliation leaves the checkpoint and all other repository and Git state unchanged.
- Ordinary orchestration resume and stale-evidence behavior remain unchanged and do not invoke reconciliation implicitly.
- The command never stages, commits, pushes, fetches, merges, deploys, changes branches, changes HEAD, modifies remotes, or accesses credentials.

## Test requirements

- Add a deterministic success test in a temporary Git repository with a named non-main branch, a deliberately pre-finalization stale checkpoint HEAD, synchronized finalized local and local origin-tracking refs, an APPROVED task, one matching APPROVE controller decision, and matching successful finalization evidence.
- Assert that success updates only the intended checkpoint and bounded reconciliation evidence, preserves all existing evidence, and invokes no worker, finalizer, or publication operation.
- Add concise parameterized failure tests for task not APPROVED, wrong task identity, main, detached HEAD, checkpoint branch mismatch, checkpoint commit mismatch, missing origin tracking ref, local/origin divergence, missing or malformed decision, unauthorized decision actor, non-APPROVE decision, decision linkage mismatch, missing or unsuccessful finalization, finalization linkage mismatch, and ambiguous evidence.
- For every negative case, assert a non-zero result and byte-for-byte preservation of the checkpoint and existing evidence.
- Add CLI parsing and exit-code coverage for the explicit command, required run identifier, successful reconciliation, and fail-closed validation errors.
- Add a regression test proving ordinary stale-evidence orchestration behavior remains unchanged and never reconciles automatically.
- Use only temporary repositories, controlled local refs, and deterministic fixture timestamps and identifiers; tests must require no network, credentials, or live remote.
- Run tests/test_orchestration.py and tests/test_agent_runner.py.
- Run the complete test suite because the command changes shared runner CLI and orchestration behavior.

## Constraints

- Treat reconciliation as recognition of previously established authority and successful finalization, never as a source of new authority.
- Validate current repository facts directly; never trust checkpoint claims alone.
- Use exact task, path, branch, commit, decision, review, and finalization linkage with no latest-match fallback when multiple candidates exist.
- Inspect only existing local Git refs; do not fetch, push, or access remote credentials.
- Permit only a named non-main branch and reject detached, unborn, missing, or ambiguous branch state.
- Fail closed before mutation on every unknown, malformed, missing, stale, conflicting, or ambiguous condition.
- Do not weaken, bypass, reorder, or reuse ordinary orchestration stale-evidence checks.
- Do not infer approval or synthesize, edit, or consume controller authority beyond validating the already-matching evidence.
- Do not repeat finalization or any Git publication action.
- Preserve evidence through append-only reconciliation details and the smallest atomic checkpoint update necessary to represent the proven terminal outcome.
- Do not delete or rewrite repository files, Git history, controller evidence, review evidence, finalization evidence, or audit evidence.
- Keep implementation small, reversible, deterministic, and confined to the allowed changed-file scope.
- Do not access secrets, credentials, tokens, network services, production systems, or production data.
- The eventual completion report must distinguish facts, assumptions, inferences, and proposals and report implemented work, files changed, database impact, tests, risks, unresolved issues, decisions required, and recommended next step.

## Owner decisions

None.

## Completion report

### Implemented

- Added the explicit preview-first `reconcile-completed-run <run-id> [--apply]` CLI command.
- Added fail-closed task, branch, local-ref, decision, review, and successful
  finalization linkage validation before mutation.
- Corrected the worker proposal during independent review so reconciliation
  follows the real review-bundle -> decision -> finalization pre/post-commit
  chain even when the interrupted checkpoint never persisted later paths.
- Added a bounded reconciliation record and atomic transition of the one named
  checkpoint to its existing `PUBLISHED` outcome.
- Added local temporary-repository unit and CLI coverage, including evidence
  preservation on rejected reconciliation.

### Files changed

- `advancore/agent_runner/orchestration.py`
- `advancore/agent_runner/__main__.py`
- `tests/test_orchestration.py`
- `docs/architecture/AGENT_RUNNER.md`
- `tasks/TASK-030-explicit-completed-run-reconciliation.md`

### Database changes

None.

### Tests executed and results

- `.venv/bin/python -m pytest tests/test_orchestration.py tests/test_agent_runner.py -q`
  — 104 passed.
- `.venv/bin/python -m pytest tests/ -q` — 641 passed.

### Assumptions

- FACT: only a `PUSHED` finalization record is treated as proof of the
  published terminal orchestration outcome.
- FACT: origin synchronization is established exclusively from the existing
  local `refs/remotes/origin/<branch>` reference.

### Risks / unresolved issues

- The command deliberately validates the existing local origin-tracking ref and
  does not fetch. It proves agreement with the last locally recorded remote tip,
  not a new network observation; this limitation is reported in preview output
  and preserves the no-credentials/no-network recovery boundary.

### Decisions required

- Independent controller review and approval are required before the bounded
  feature-branch implementation may be finalized or pushed.

### Recommended next step

Review the repaired evidence-chain validation and refreshed 641-test result,
then use the existing controller-decision and finalization boundaries.
