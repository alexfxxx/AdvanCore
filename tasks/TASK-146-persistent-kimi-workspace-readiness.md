# TASK-146 — Persistent Kimi Workspace Readiness Foundation

STATUS: COMPLETE

## Objective

Add a read-only controller preflight for a dedicated persistent Kimi worker
worktree so workspace trust can be reused without weakening repository,
credential or approval boundaries.

## Business context

Kimi Code v0.38 successfully completed both an ordinary bounded run and a real
two-agent Swarm smoke test under TASK-144. Recreating a new worker worktree for
every attempt causes repeated workspace-trust friction. The owner approved a
persistent dedicated Kimi worktree, while requiring the controller to retain
all task approval, scope verification and Git publication authority.

Kimi Swarm sub-agents may cooperate inside one governed worktree. Separately
queued Kimi, Gemini and Codex tasks still require distinct non-overlapping
worktrees and the TASK-145 reservation boundary.

## In scope

- Add a read-only readiness inspector for an already-created persistent Kimi
  Git worktree.
- Require a real, owner-controlled, non-symlink worktree belonging to the same
  Git common directory as the controller repository.
- Require a clean index/worktree, a non-detached governed feature branch, and
  the shared common-directory remote configuration before it is eligible.
- Report bounded reason codes suitable for controller telemetry; store no
  prompts, Git URLs, environment values, credentials or command output.
- Document the owner-attended one-time worktree creation and Kimi trust step.
- Add deterministic tests with mocked bounded Git probes.

## Out of scope

- Creating, deleting, resetting, cleaning, cloning or switching a worktree.
- Running `kimi /trust`, logging in, refreshing OAuth, changing Kimi versions,
  installing software or broadening filesystem access.
- Worker launch, task approval, scope reservation, publication, merge,
  deployment, PostgreSQL, Alembic, migrations or real data.
- GitHub, database, SSH, Gemini, Codex or Docker credential access.

## Allowed changed-file scope

- `tasks/TASK-146-persistent-kimi-workspace-readiness.md`
- `advancore/agent_runner/persistent_worker_workspace.py`
- `tests/test_persistent_worker_workspace.py`
- `docs/runbooks/PERSISTENT_KIMI_WORKSPACE.md`

## Database impact

None.

## Acceptance criteria

- [x] An eligible clean persistent Kimi worktree is identified without
      mutation.
- [x] Symlinked, foreign-repository, dirty, detached, base-branch or ambiguous
      worktrees fail closed with bounded reason codes.
- [x] No raw Git URL, environment, prompt, output or credential is returned or
      persisted.
- [x] No helper can create, reset, clean, switch, trust or launch anything.
- [x] Focused tests, full tests and `git diff --check` pass.

## Owner decisions

Approved on 28 August 2026 as the non-account groundwork for the persistent
Kimi worker-worktree approach. The one-time Kimi trust/authentication and any
CLI upgrade remain owner-attended.

## Completion report

### Implemented

- Added a read-only persistent-worktree inspector with bounded readiness reason
  codes and no path, remote, environment, prompt or output projection.
- Required the same Git common directory, a clean `task-*` branch, a real
  owner-controlled non-symlink directory and successful bounded local probes.
- Added an operations runbook that keeps creation, cleanup, branch switching,
  Kimi trust, authentication, upgrades and worker launch outside this service.

### Worker routing evidence

- Codex implemented this controller-only prerequisite because a trusted
  persistent Kimi worktree does not exist yet; creating and trusting that
  worktree remains the later owner-attended step this task prepares.
- No provider login, credential access, upgrade or worker launch was attempted.

### Database changes

None.

### Verification

- Focused tests: 5 passed.
- Full isolated suite: 1,314 passed, 2 skipped.
- `git diff --check`: passed.

### Decisions required

None for the readiness foundation. Actual worktree creation and Kimi trust are
deliberately deferred to an owner-attended session.
