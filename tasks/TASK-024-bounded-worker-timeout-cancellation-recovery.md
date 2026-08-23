# TASK-024 — Bounded Worker Timeout, Cancellation, and Recovery

STATUS: APPROVED

## Objective

Make local implementation-worker execution bounded and safely recoverable when
a provider hangs or an operator interrupts it, while preserving fail-closed
fallback, controller, and publication boundaries.

## Business context

The TASK-023 operational run showed that Kimi could return an eligible
availability failure and Codex fallback could start correctly, but a long-running
worker offered no bounded timeout or governed cancellation result. Manual
interruption left an allowed partial file and required controller diagnosis.
Exception-based operation requires deterministic worker termination, Git-state
evidence, and one safe recovery instruction instead of an indefinite wait.

## In scope

1. Replace worker subprocess execution with one shared, code-owned bounded
   process runner used by Kimi, Kimi-Swarm, and Codex adapters.
2. Add a conservative default worker timeout and an explicitly bounded CLI/
   orchestration override. Reject zero, negative, excessive, malformed, or
   ambiguous values.
3. Launch each worker in its own process group/session and, on timeout or
   cancellation, terminate the complete local worker process group with a
   bounded graceful period followed by forced termination if required.
4. Convert timeout and cancellation into bounded structured `WorkerResult`
   evidence without raw transcripts, environment dumps, prompts, or credentials.
5. Classify timeout/cancellation as non-fallback conditions. Never launch a
   second worker because the first timed out or was interrupted.
6. After termination, independently snapshot branch, HEAD, index, worktree, and
   remotes. Any mutation or ambiguity stops for controller review.
7. When state is unchanged, report one exact recovery action: explicitly resume
   or start a separately reviewed worker invocation. Never silently retry.
8. Persist timeout policy and terminal reason in orchestration checkpoints and
   bounded auto/orchestration evidence so resume cannot silently change it.
9. Keep preview side-effect free and retain all TASK-017 through TASK-023
   verification, controller, and TASK-020 publication gates.
10. Add deterministic tests using short-lived fake processes, including a child
    process, to prove timeout cleanup and no orphaned worker remains.

## Out of scope

- Automatic retry after timeout/cancellation.
- Treating timeout/cancellation as provider availability fallback.
- Arbitrary signals, commands, executable paths, or user-controlled process policy.
- Controller self-approval, automatic publication, merge, deployment, or `main`.
- Credentials, cloud/remote execution, web search, or sandbox bypass.

## Allowed changed-file scope

1. `advancore/agent_runner/worker.py`
2. `advancore/agent_runner/auto_pipeline.py`
3. `advancore/agent_runner/orchestration.py`
4. `advancore/agent_runner/__main__.py`
5. `advancore/agent_runner/__init__.py`
6. `tests/test_worker_timeout.py` (new)
7. `docs/architecture/AGENT_RUNNER.md`
8. `docs/runbooks/WORKER_FALLBACK.md`
9. `docs/decisions/ADR-024-bounded-worker-timeout-cancellation-recovery.md` (new)
10. `tasks/TASK-024-bounded-worker-timeout-cancellation-recovery.md`

No other file may change.

## Acceptance criteria

1. All production implementation adapters use the shared bounded process runner.
2. Default and maximum timeout values are code-owned and tested.
3. Timeout ends the worker process group, including a spawned child, within a
   bounded cleanup interval.
4. Keyboard interruption performs the same cleanup before returning/raising a
   governed terminal result.
5. Timeout/cancellation never invokes fallback or repair automatically.
6. Clean and mutated post-termination Git states produce distinct bounded reports.
7. Checkpoint resume retains the original timeout policy.
8. Reports contain terminal reason and recovery action but no raw output.
9. Full repository test suite passes.
10. Exact changed paths equal the ten allowed paths.

## Required verification

```bash
.venv/bin/python -m pytest tests/test_worker_timeout.py -v
.venv/bin/python -m pytest tests/ -v
git diff --check
```

## Owner decisions

The owner approved proceeding with TASK-024 on `agent-control-foundation` and
approved Codex or another registered worker when Kimi is unavailable. This does
not authorize unsafe process controls, silent retry/fallback, controller
self-approval, `main`, merge, or deployment.

## Completion report

### Implemented

- Shared bounded process runner for all production adapters, strict timeout
  policy, process-group cancellation, bounded Git evidence, recovery action,
  non-fallback/non-repair classification, CLI/orchestration persistence, tests,
  architecture documentation, runbook, and ADR.

### Files changed

- The ten paths declared in this task's allowed changed-file scope.

### Database changes

- None.

### Tests and results

- `.venv/bin/python -m pytest tests/test_worker_timeout.py -v` — 7 passed.
- `.venv/bin/python -m pytest tests/ -v` — 580 passed.
- `git diff --check` — passed.

### Assumptions

- A 1,800-second default, 7,200-second maximum, and one-second graceful period
  are conservative local execution bounds.

### Risks / unresolved issues

- No known implementation defects. Process-group signalling is POSIX-specific,
  matching the approved local macOS/Linux execution environment.

### Decisions required

- Independent controller/owner review; implementation does not self-approve.

### Recommended next step

- Review the bounded evidence and required verification results before any
  approval or publication action.
