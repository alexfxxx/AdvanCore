# TASK-149 — Controller-Mediated Persistent Kimi Swarm Launch

STATUS: COMPLETE

## Objective

Connect the persistent trusted Kimi worktree to the existing controller-owned
queue, reservation, manifest, eligibility and worker-adapter boundaries without
creating a second orchestration or publication path.

## Business context

TASK-143 through TASK-148 established the fail-closed evidence needed before a
Kimi Swarm launch. The owner has now created and trusted one persistent Git
worktree and proved both Kimi and a two-agent Swarm can run there. The controller
needs one narrow service that consumes those existing proofs, launches only the
registered sandboxed adapter and returns bounded evidence to the existing
fallback/orchestration layer.

## In scope

- Require an already-`RUNNING` TASK-143 queue claim and matching active TASK-145
  `kimi-swarm` reservation.
- Reinspect TASK-146 persistent-worktree readiness immediately before launch.
- Verify the TASK-147 manifest from disk and bind fresh TASK-148 eligibility
  evidence to the exact task, path set and branch.
- Invoke only the existing registered `KimiSwarmWorkerAdapter`; accept no
  executable, argument array, environment or free-form command from a caller.
- Build the worker instruction from the governed task path and exact allowed
  scope.
- After the worker returns, independently reject branch or HEAD movement,
  staged changes, manifest tampering and any out-of-scope changed path.
- Bind launch to the exact no-follow worktree directory identity and atomically
  consume each queue-claim/reservation pair once, including across processes.
- Store crash-durable receipts in fixed owner application state outside both
  repositories and compact only evidence whose reservation has expired.
- Return bounded launch metadata suitable for the existing fallback router;
  never persist prompts, commands, PATH values, raw stdout or raw stderr.
- Add deterministic tests and an operator runbook.

## Out of scope

- Queue claim/finish, reservation acquire/release or manifest preparation.
- Worktree create, reset, clean, switch, trust, login or CLI upgrade.
- Changing Kimi → Gemini → Codex routing or self-selecting a worker.
- Tests/repairs after implementation, approval, staging, commit, push, PR,
  merge, deployment, Docker, database or migration operations.
- Exposing GitHub, database, SSH, Docker, Gemini, Codex or controller secrets.

## Allowed changed-file scope

- `tasks/TASK-149-controller-mediated-kimi-swarm-launch.md`
- `advancore/agent_runner/persistent_kimi_launch.py`
- `advancore/agent_runner/__init__.py`
- `tests/test_persistent_kimi_launch.py`
- `docs/runbooks/PERSISTENT_KIMI_LAUNCH.md`

## Database impact

None.

## Acceptance criteria

- [x] Launch occurs only once when queue, reservation, workspace, on-disk manifest
      and explicit architecture/multi-file eligibility all match.
- [x] The existing sandboxed Kimi-Swarm adapter is the only execution path.
- [x] Every preflight, worker and post-run failure returns a bounded result and
      launches no fallback or publication action by itself.
- [x] Branch/HEAD movement, staged changes, manifest changes and out-of-scope
      paths fail closed; replacement worktree paths and replayed or concurrent
      launches are also rejected.
- [x] Focused tests, full tests and `git diff --check` pass.

## Owner decisions

Approved on 28 August 2026 by the owner's instruction to proceed after the
persistent worktree trust, OAuth, normal Kimi and two-agent Swarm smoke tests
all passed. No further business, database or credential decision is required.

## Completion report

- Bugbot final review: clean after bounded repair cycles.
- Focused launch-boundary tests: 24 passed.
- Local dependency-independent regression suite: 1,411 passed, 2 skipped.
- The five FastAPI test modules are deferred to GitHub CI because the shared
  local virtual environment does not contain FastAPI; no dependency was
  installed or changed for this task.
- `py_compile` and `git diff --check`: passed.
