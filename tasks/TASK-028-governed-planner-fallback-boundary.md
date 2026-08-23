# TASK-028 — Governed Planner Fallback Boundary

STATUS: APPROVED

## Objective

Add an explicit, bounded, provider-neutral planner fallback so owner-goal task
generation can continue when Kimi is unavailable, while ensuring planners are
read-only proposal sources and `agent_runner` remains the only DRAFT constructor.

## Business context

TASK-022 added implementation-worker fallback, and TASK-024 bounded worker
processes. The end-to-end owner-goal path still has a single-provider gap:
orchestration planner choices are Kimi/Kimi-Swarm or dry-run, with no Codex
fallback, and proposal-only planner calls bypass the shared bounded process
runner. This prevents unattended goal intake when Kimi is unavailable.

Planner fallback is not implementation fallback. A planner may return one
bounded proposal, but cannot write task files, change Git, approve scope, or
execute implementation. `agent_runner.goal_task` must continue to parse,
validate, construct, and write the DRAFT.

## In scope

1. Define a fixed code-owned registry of approved proposal planners, initially
   `dry-run`, `kimi`, `kimi-swarm`, and `codex`.
2. Add a proposal-only Codex planner adapter using fixed argv, ephemeral mode,
   read-only sandboxing, denied interactive approvals, verified repository root,
   bounded timeout/process-group cleanup, and one bounded prompt.
3. Prohibit planner web search, cloud/remote execution, additional writable
   roots, arbitrary config/argv, credentials, sandbox bypass, and task/Git writes.
4. Route Kimi and Kimi-Swarm proposal planners through the shared TASK-024
   bounded process runner without granting implementation behavior.
5. Add explicit policy equivalent to
   `--planner kimi-swarm --fallback-planner codex`. Default remains one planner
   with no fallback.
6. Permit at most one fallback, only for deterministic executable, quota/
   capacity, or authentication availability failure and only after independently
   proving branch, HEAD, index, worktree, and remotes unchanged.
7. Timeout, cancellation, malformed proposal, validation failure, ambiguous
   error, or any Git mutation must stop without fallback.
8. Persist primary/fallback/terminal planner, timeout, failure classification,
   integrity result, and bounded recovery evidence in goal-task artifacts and
   orchestration checkpoints/reports. Never persist transcripts or credentials.
9. Resume must retain checkpointed planner policy and reject any silent override.
10. Extend standalone `goal-task` and `orchestrate` CLI paths with registered
    Codex planner and optional explicit fallback.
11. Preserve TASK-019 proposal validation: planner output is untrusted data;
    only the runner assigns IDs, paths, schema, and `STATUS: DRAFT`.
12. Add tests for safe Codex argv, bounded planner termination, eligible fallback,
    mutation/unknown/malformed/timeout stops, single hop, persistence, resume,
    and no planner-authored file authority.

## Out of scope

- Planner implementation, task-file writes, lifecycle approval, worker execution, or publication.
- Automatic or silent fallback.
- More than one fallback hop.
- Natural-language owner decision inference.
- Credentials, network APIs, remote/cloud execution, merge, deployment, or `main`.

## Allowed changed-file scope

1. `advancore/agent_runner/worker.py`
2. `advancore/agent_runner/goal_task.py`
3. `advancore/agent_runner/orchestration.py`
4. `advancore/agent_runner/__main__.py`
5. `advancore/agent_runner/__init__.py`
6. `tests/test_planner_fallback.py` (new)
7. `docs/architecture/AGENT_RUNNER.md`
8. `docs/decisions/ADR-028-governed-planner-fallback-boundary.md` (new)
9. `tasks/TASK-028-governed-planner-fallback-boundary.md`

No other file may change.

## Acceptance criteria

1. Codex planner uses read-only, fixed, bounded execution and cannot write tasks.
2. Kimi proposal planners use the shared bounded runner.
3. Explicit clean availability failure selects exactly one configured fallback.
4. Timeout/cancellation, mutation, malformed proposal, and unknown failure stop.
5. `agent_runner` remains the sole DRAFT constructor and validator.
6. Checkpoints/artifacts retain bounded planner policy/evidence across resume.
7. Defaults remain no fallback and preview remains side-effect free.
8. Full repository test suite passes and exact changed paths stay within scope.

## Required verification

```bash
.venv/bin/python -m pytest tests/test_planner_fallback.py -v
.venv/bin/python -m pytest tests/ -v
git diff --check
```

## Owner decisions

The owner explicitly authorized Codex or another approved worker fallback and
continued bounded development. Planner fallback remains proposal-only and does
not spend approval, implementation, or publication authority.

## Completion report

### Implemented

- Added a fixed proposal-planner registry with dry-run, Kimi, Kimi-Swarm, and
  read-only Codex adapters.
- Routed executable planners through bounded execution and added one-hop,
  explicit availability fallback guarded by independent Git integrity checks.
- Persisted bounded planner policy, terminal selection, classification,
  integrity, timeout, and recovery evidence in artifacts/checkpoints.
- Added CLI policy/timeout options and checkpoint-bound resume enforcement.
- Added focused tests and architecture/decision documentation.

### Files changed

- `advancore/agent_runner/worker.py`
- `advancore/agent_runner/goal_task.py`
- `advancore/agent_runner/orchestration.py`
- `advancore/agent_runner/__main__.py`
- `advancore/agent_runner/__init__.py`
- `tests/test_planner_fallback.py`
- `docs/architecture/AGENT_RUNNER.md`
- `docs/decisions/ADR-028-governed-planner-fallback-boundary.md`
- `tasks/TASK-028-governed-planner-fallback-boundary.md`

### Database changes

None.

### Tests and results

- `.venv/bin/python -m pytest tests/test_planner_fallback.py -v` — 12 passed.
- `.venv/bin/python -m pytest tests/ -q` — 613 passed.
- `git diff --check` — passed.

### Assumptions

- FACT: planner fallback is proposal-only and does not convey implementation,
  lifecycle, publication, or task-file authority.
- ASSUMPTION: the existing strict worker-timeout bounds are also appropriate
  for planner timeout input, with a shorter code-owned planner default.

### Risks / unresolved issues

- Local provider CLI versions may change their accepted fixed arguments; such a
  change must fail closed and be reviewed before the registry is updated.

### Decisions required

None for implementation. Owner/reviewer approval remains required; this worker
did not change task lifecycle status or self-approve.

### Recommended next step

Review the diff and verification evidence, then make the explicit lifecycle
decision. Do not commit until approved.
