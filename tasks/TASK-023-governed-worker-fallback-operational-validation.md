# TASK-023 — Governed Worker Fallback Operational Validation

STATUS: READY

## Objective

Prove the TASK-022 worker fallback boundary through realistic, deterministic
integration tests and document the exception-based operating procedure, without
adding new authority or depending on a live AI provider in the test suite.

## Business context

TASK-022 added an explicit Kimi/Kimi-Swarm to Codex fallback path. This task
closes the milestone by validating the real adapter/subprocess boundary and the
fail-closed conditions operators depend on. The task itself should be executed
with Kimi-Swarm as primary and Codex as the explicitly approved fallback so the
new path is exercised operationally when Kimi remains unavailable.

## In scope

1. Add integration tests using temporary repositories and fake executables on
   an isolated PATH to exercise the real argv/subprocess adapters without live
   provider calls.
2. Prove one successful primary-provider availability failure to explicit
   Codex fallback, followed by the existing verification path.
3. Prove unknown failure and any branch, HEAD, index, worktree, or remote
   mutation stop without fallback.
4. Prove there is at most one fallback hop and a failed fallback never chains.
5. Prove CLI defaults contain no fallback and invalid/duplicate/dry-run policy
   combinations fail closed.
6. Prove reports and persisted evidence identify primary, classified reason,
   fallback, and terminal worker without raw transcripts or credentials.
7. Add a concise operator runbook covering selection, safe invocation,
   expected stops, evidence review, resume behavior, and the continuing
   controller/publication gates.
8. Update architecture/decision documentation with operational validation
   results and the permanent-versus-local responsibility split.

## Out of scope

- Adding another production worker adapter.
- Live-provider calls in automated tests.
- Automatic controller approval, commit, push, merge, deployment, or `main` changes.
- Credentials, remote/cloud execution, arbitrary commands, or permission bypasses.
- More than one fallback attempt.

## Allowed changed-file scope

1. `tests/test_worker_fallback_integration.py` (new)
2. `docs/runbooks/WORKER_FALLBACK.md` (new)
3. `docs/architecture/AGENT_RUNNER.md`
4. `docs/decisions/ADR-023-worker-fallback-operational-validation.md` (new)
5. `tasks/TASK-023-governed-worker-fallback-operational-validation.md`

No other file may change.

## Acceptance criteria

1. Integration tests exercise real worker adapter subprocess construction with
   isolated fake executables and no network/provider dependency.
2. Eligible clean availability failure selects exactly the configured fallback.
3. Unknown failure and every ambiguous/mutated Git condition block fallback.
4. Failed fallback is terminal and cannot trigger a third worker.
5. Reports/artifacts contain bounded identity and decision evidence only.
6. Runbook preserves `agent_runner`, controller, and TASK-020 authority boundaries.
7. Full repository test suite passes.
8. Exact changed paths equal the five allowed paths.

## Required verification

```bash
.venv/bin/python -m pytest tests/test_worker_fallback_integration.py -v
.venv/bin/python -m pytest tests/ -v
git diff --check
```

## Owner decisions

The owner approved proceeding through TASK-023 and explicitly approved Codex
or another registered worker as fallback. This authorizes TASK-023 execution
with `--worker kimi-swarm --fallback-worker codex`; it does not authorize
self-approval, unsafe permissions, `main`, merge, or deployment.

## Completion report

### Implemented

### Files changed

### Database changes

### Tests and results

### Assumptions

### Risks / unresolved issues

### Decisions required

### Recommended next step
