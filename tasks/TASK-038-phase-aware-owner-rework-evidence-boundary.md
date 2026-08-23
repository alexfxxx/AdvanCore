# TASK-038 — Phase-aware owner rework evidence boundary

STATUS: READY

## Objective

Permit one explicitly authorized owner rework cycle on a reviewed dirty worktree without creating a general dirty-worktree bypass: freeze exact reviewed content before launch, then allow the selected worker to change only the same reviewed paths while repository identity, scope, Git safety, and fresh-review requirements remain fail-closed.

## Business context

Owner-requested rework currently cannot safely resume from a reviewed implementation. TASK-037 proved that one fingerprint cannot serve both phases: exact content must remain unchanged before launch, but a legitimate rework worker must be able to update that content after launch. The permanent controller needs phase-specific validation so the owner is not a stage-by-stage courier and no worker can broaden its own authority.

## Facts

- The clean approved TASK-037 specification is the only source baseline; unpublished TASK-035, TASK-036, and TASK-037 implementations are not completion evidence.
- `agent_runner` remains the authority boundary, approved workers remain replaceable implementation providers, and GitHub remains source of truth.
- A typed evidence object is a narrow single-use capability, not a dirty-tree boolean.
- Pre-launch validation must prove the exact reviewed baseline is unchanged.
- Post-launch validation must permit content evolution only on the already bound tracked unstaged path set.
- Branch, HEAD, index cleanliness, remotes, remote refs, repository integrity, authorized scope, Git-state shape, and evidence identity remain protected throughout.
- The task lifecycle may alter only this task's single `STATUS:` line before worker launch.
- No new repository file is authorized other than this governing TASK-038 record.

## In scope

- Introduce typed immutable-for-validation owner rework evidence created only after one exact matching owner `REWORK_IMPLEMENTATION` decision.
- Bind task, orchestration run, prior review bundle, handoff, decision, bounded owner note, branch, HEAD, clean index, allowed scope, exact tracked unstaged paths, per-file content hashes, normalized task hash, binary diff hash, remote configuration, remote refs, repository integrity, evidence version, phase, and consumption identity.
- Provide separate baseline and terminal validation operations rather than a permissive flag.
- Baseline validation, immediately before primary or eligible fallback launch, must recompute and match all identities and exact content. Only this task's single lifecycle `STATUS:` line may differ after normalization.
- Terminal validation, after worker success or failure and after each repair, must recompute branch, HEAD, clean index, remotes, refs, integrity, exact path set, allowed scope, and unambiguous tracked-unstaged Git state. Content may differ from the baseline only on the exact bound path set.
- Reject added or missing paths, paths outside scope, staged or mixed changes, untracked or intent-to-add files, rename, deletion, mode change, conflict, duplicate path, malformed status, stale/replayed/consumed evidence, or any protected repository mutation.
- Independently enforce the evidence in both runner and auto-pipeline boundaries.
- Validate again before fresh review-bundle and handoff creation; those artifacts must describe the terminal content and must not reuse the prior bundle or handoff.
- Preserve prior and failure evidence without reset, discard, staging, commit, push, or publication.
- Preserve current fallback eligibility, one-hop limit, repair budget, owner gates, finalization policy, and all unrelated clean-tree behavior.
- Add regression and real-Git end-to-end coverage only to the four existing authorized test files.
- Update existing architecture and owner-resume documentation.

## Explicitly out of scope

- Reusing or completing any unpublished implementation.
- A general dirty-tree override, naked boolean, path-only authorization, inferred owner intent, worker-created owner evidence, or self-approval.
- Allowing a worker to add, remove, rename, stage, untrack, mode-change, or broaden the reviewed path set.
- Changing worker/fallback policy, budgets, timeouts, owner actions, publication policy, or unrelated architecture.
- Projects functionality, Streamlit pages, business rules, database schema or migrations, production data, deployment, credentials, secrets, or live-provider access.
- Main, staging, commit, push, merge, tag, branch switch, reset, rebase, remote mutation, publication, or history rewrite.
- Any new source, test, documentation, fixture, helper, migration, or task file other than this TASK-038 record.

## Allowed changed-file scope

- `advancore/agent_runner/orchestration.py`
- `advancore/agent_runner/auto_pipeline.py`
- `advancore/agent_runner/runner.py`
- `advancore/agent_runner/validation.py`
- `tests/test_orchestration.py`
- `tests/test_auto_pipeline.py`
- `tests/test_agent_runner.py`
- `tests/test_owner_action_orchestration_e2e.py`
- `docs/architecture/AGENT_RUNNER.md`
- `docs/runbooks/OWNER_DECISION_RESUME.md`
- `tasks/TASK-038-phase-aware-owner-rework-evidence-boundary.md`

## Database impact

None.

## Safety requirements

- Initial execution outside an exact owner rework remains clean-tree only.
- Evidence is created only after the matching current owner decision is validated.
- Workers cannot approve tasks or implementations, create owner decisions, change policy, or publish.
- Unknown, missing, malformed, conflicting, stale, replayed, consumed, ambiguous, or mutated state fails closed.
- No staging, commit, push, merge, deployment, reset, discard, remote mutation, or history rewrite is performed by implementation or verification.

## Acceptance criteria

- A typed evidence object, never a boolean, is the sole capability for rework execution on a dirty reviewed baseline.
- Evidence is bound to the exact current task, run, prior bundle, prior handoff, owner decision, note, branch, HEAD, scope, path set, baseline contents and binary diff, index, remotes, refs, integrity, schema version, and single-use identity.
- Baseline validation rejects any same-path content mutation and every protected identity or repository mismatch before primary and fallback launch.
- The exact single `STATUS:` lifecycle change in TASK-038 is accepted after normalization; every other task-content change and every other task-file change is rejected.
- Terminal validation permits worker content changes only on the exact baseline path set and rejects any path-set, scope, Git-state, branch, HEAD, index, remote, ref, integrity, identity, or evidence mutation.
- Terminal validation runs after worker success and failure, after every repair, and before fresh review and handoff generation.
- An eligible fallback is invoked at most once and only after a new successful baseline validation.
- Bounded repairs remain capped by existing policy and stop immediately after protected-state loss.
- Successful rework creates a new review bundle and new handoff bound to terminal content; prior evidence cannot authorize another launch.
- Failure preserves reviewed files and all historical evidence without false success or publication.
- Runner and auto-pipeline each independently reject missing, malformed, stale, replayed, or mismatching evidence.
- Unrelated initial execution, clean-tree validation, finalization, publication, and completed-run reconciliation behavior is unchanged.
- Only allowed changed-file scope is modified and no new file exists other than TASK-038.

## Test requirements

- Add a real-Git end-to-end test in `tests/test_owner_action_orchestration_e2e.py` covering prior reviewed dirty content, exact owner REWORK decision, typed evidence capture, lifecycle STATUS-only transition, controlled worker content update on the same paths, full verification, and fresh review bundle plus handoff.
- Do not mock branch, HEAD, status, path set, per-file content, binary diff, remotes, remote refs, or integrity in that acceptance path.
- Test every baseline and terminal checkpoint: before primary, before fallback, after terminal success, after terminal failure, after each repair, before fresh review, and before fresh handoff.
- Test same-path pre-launch mutation rejection and same-path post-launch content acceptance.
- Test extra, missing, outside-scope, staged, mixed, intent-to-add, untracked, renamed, deleted, mode-changed, conflicted, duplicated, and malformed states.
- Test branch, HEAD, index, remote configuration, remote-ref, repository-integrity, bundle, handoff, decision, task, run, note, scope, path-set, phase, consumption, and evidence-hash mismatch.
- Test exact STATUS-only normalization and reject non-STATUS or multiple task mutations.
- Test eligible fallback once, ineligible fallback never, repair limit, post-repair protected-state mutation, and failure preservation.
- Put all test changes only in `tests/test_orchestration.py`, `tests/test_auto_pipeline.py`, `tests/test_agent_runner.py`, and `tests/test_owner_action_orchestration_e2e.py`.
- Run the four focused test files, then the full `tests/` suite with the repository's local test database setting.
- Run Python compilation/import sanity checks, `git diff --check`, exact scope verification, and new-file verification.

## Constraints

- Prefer small, explicit phase-aware validators over broad rewrites.
- Durable evidence stores bounded identities and hashes, not raw source, diffs, prompts, credentials, environment dumps, or production data.
- The owner note is context only and cannot expand paths, authority, policy, or budgets.
- If safe terminal content evolution cannot be separated from protected repository identity, stop for controller review.
- Completion requires the report mandated by AGENTS.md.

## Owner decisions

None.

## Completion report

### Implemented

### Files changed

### Database changes

### Tests executed and results

### Assumptions

### Risks / unresolved issues

### Decisions required

### Recommended next step
