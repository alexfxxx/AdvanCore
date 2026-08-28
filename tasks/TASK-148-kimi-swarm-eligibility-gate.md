# TASK-148 — Kimi Swarm Eligibility Gate

STATUS: COMPLETE

## Objective

Add a pure controller decision gate that determines whether an explicitly
assigned governed task is eligible for Kimi Swarm, without launching a worker
or changing any approval, repository or credential state.

## Business context

Kimi Swarm is useful for broad multi-file implementation or explicitly
classified architecture work, while ordinary Kimi is more efficient for small
changes. TASK-144 proved a real two-agent Swarm run on installed Kimi v0.38;
TASK-145 reserves non-overlapping paths, TASK-146 inspects a persistent
worktree, and TASK-147 prepares the exact scope manifest. The controller needs
one deterministic gate combining those facts before future launch integration.

## In scope

- Add a pure, immutable eligibility input/result model with bounded reason
  codes.
- Require an explicit `kimi-swarm` assignment and a `RUNNING` queue claim for
  the same canonical task.
- Require an active `kimi-swarm` TASK-145 reservation for exactly the same
  case-insensitive path set.
- Require TASK-146 workspace readiness and exact TASK-147 manifest verification.
- Treat work as suitable only when either:
  - the governed exact scope contains at least 11 paths; or
  - the controller explicitly classifies it as architecture work.
- Reject empty, unsafe, duplicate, case-only or mismatched scope evidence.
- Add deterministic tests and an operations runbook.

## Out of scope

- Worker launch, Swarm command construction, sub-agent count or concurrency.
- Inferring architecture work from free text or letting an AI self-select Swarm.
- Worktree creation/cleanup/switching, Kimi trust/login/upgrade or credentials.
- Queue transitions, reservation acquisition/release, manifest writing, fallback
  routing, staging, commit, push, PR, merge, deployment or database changes.

## Allowed changed-file scope

- `tasks/TASK-148-kimi-swarm-eligibility-gate.md`
- `advancore/agent_runner/kimi_swarm_eligibility.py`
- `tests/test_kimi_swarm_eligibility.py`
- `docs/runbooks/KIMI_SWARM_ELIGIBILITY.md`

## Database impact

None.

## Acceptance criteria

- [x] Matching explicit queue, reservation, workspace and manifest evidence can
      produce an eligible decision for suitable work.
- [x] Every missing, mismatched, unsafe or unsuitable input fails closed with a
      bounded reason code.
- [x] No method can mutate state or launch/select a worker by itself.
- [x] Focused tests, full tests and `git diff --check` pass.

## Owner decisions

Approved on 28 August 2026 as the last unattended foundation step before
owner-attended persistent-worktree creation/trust and later launch integration.
Swarm remains one governed task in one worktree; separate simultaneous tasks
remain isolated through separate worktrees and TASK-145 reservations.

## Completion report

- Added an immutable, side-effect-free controller gate for explicit Kimi Swarm
  eligibility decisions.
- Required matching TASK-143 queue ownership, TASK-145 path reservation,
  TASK-146 workspace readiness and TASK-147 scope-manifest verification.
- Kept worker launch, worker selection, repository mutation, credentials and
  approval actions outside this component.
- Verification on 28 August 2026:
  - focused suite: `14 passed`;
  - full suite: `1377 passed, 2 skipped`;
  - changed-file scope: the four allowed TASK-148 files only.
