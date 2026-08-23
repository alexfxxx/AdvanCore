# TASK-028 — Governed Planner Fallback Boundary

STATUS: READY

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

### Files changed

### Database changes

### Tests and results

### Assumptions

### Risks / unresolved issues

### Decisions required

### Recommended next step
