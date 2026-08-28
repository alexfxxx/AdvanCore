# Persistent Kimi Worker Workspace

AdvanCore may reuse one dedicated Kimi Git worktree to avoid repeating
workspace-trust setup for every governed Kimi or Kimi Swarm attempt. Kimi Swarm
sub-agents cooperate inside that one task worktree; separately queued workers
still require distinct non-overlapping worktrees and TASK-145 reservations.

The controller readiness check is read-only. It requires the dedicated path to
be a real owner-controlled linked worktree from the same local Git repository,
which also binds it to the same shared remote configuration. It must be on a
clean `task-*` feature branch. Missing,
symlinked, foreign, dirty, detached, base-branch or ambiguous state fails closed.
The check returns only a reason code and optional safe branch name.

One-time creation and `kimi /trust` remain owner-attended. The controller must
not create trust, initiate login, upgrade Kimi, reset, clean, delete, clone or
switch the worktree through this readiness service. It must rerun readiness
immediately before every governed launch.

Readiness grants no task approval, execution authority, database access,
credential access or Git publication authority. `agent_runner` remains the
authority boundary, and exact scope verification remains mandatory after every
worker attempt.
