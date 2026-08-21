# ADR-017 — Governed Swarm Auto-Pipeline

## Status

Accepted — implemented as part of TASK-017.

## Context

TASK-005 through TASK-016 established a governed local agent runner with task
discovery, safety validation, worker adapter boundary, post-worker verification,
audit trail, review bundles, controller decisions, handoff/reconciliation,
adapter boundary, transport envelope, and transport-driver boundary.

The remaining operational friction is the number of manual commands an
owner/controller must run for every task. The goal is to automate only the safe
pre-publication portion (validation, worker launch, review bundle, full pytest,
`git diff --check`, exact scope verification, and a consolidated report) while
keeping staging, commit, push, merge, deployment, controller approval, and
lifecycle approval explicitly gated.

Kimi Swarm is the preferred implementation worker, but it must remain a worker
only and inherit the same governance restrictions as any other worker.

## Decision

Introduce a governed auto-pipeline under `advancore/agent_runner/auto_pipeline.py`
with a single CLI entry point:

```bash
.venv/bin/python -m advancore.agent_runner auto TASK-018 --worker kimi-swarm
```

The pipeline:

1. Resolves and parses the approved task file.
2. Parses and validates the task's `Allowed changed-file scope` section.
3. Reuses `execute()` for branch/clean/status validation, worker launch,
   pre/post Git snapshots, audit record, and review bundle.
4. Detects any staged/index changes created by the worker.
5. Runs the full repository pytest suite via the existing command convention.
6. Runs `git diff --check` on both unstaged and staged changes.
7. Compares actual changed paths (tracked modifications, untracked files,
   deletions, rename targets) against the allowed scope.
8. Writes a bounded JSON Lines artifact under `.agent_runner/auto/`.
9. Produces a controller-ready consolidated report.

The pipeline fails closed on the first failing gate and never stages, commits,
pushes, merges, switches branches, deploys, or mutates lifecycle state.

### Scope parsing and enforcement

Task files may include an `## Allowed changed-file scope` section listing
backtick-quoted repository-relative paths. The pipeline:

- rejects auto mode if the section is missing,
- rejects unsafe allowed paths (absolute, `..`, or repository escape),
- rejects any actual changed path outside the allowed set.

### Kimi Swarm invocation

The installed Kimi CLI (v0.38.0 at implementation time) does not expose a
documented non-interactive `AgentSwarm` subcommand. Therefore the
`KimiSwarmWorkerAdapter` uses the same safe `kimi --prompt <instruction>`
boundary as `KimiWorkerAdapter` and sends a canonical instruction that:

- explicitly requests Kimi's AgentSwarm capability for implementation/review,
- restates the task's allowed changed-file scope,
- lists prohibited actions (no staging, commit, push, merge, branch switch,
  credential access, deployment, self-approval),
- requires a completion report and git status.

The adapter does not add `--auto`, `--yolo`, or equivalent permission-bypass
flags and does not silently fall back to unrestricted autonomous modes.

### Result model

The pipeline reports explicit terminal states:

- `READY_FOR_APPROVAL`
- `VALIDATION_FAILED`
- `WORKER_FAILED`
- `POST_WORKER_VERIFICATION_FAILED`
- `TEST_FAILED`
- `DIFF_CHECK_FAILED`
- `SCOPE_FAILED`
- `ARTIFACT_FAILED`

A passing run means only:

```
IMPLEMENTATION + VERIFICATION COMPLETE → READY FOR CONTROLLER/OWNER REVIEW
```

It never means approved, committed, pushed, merged, or deployed.

## Consequences

- Repetitive operator commands are reduced to approximately one execution command
  plus one owner/controller approval decision.
- Existing TASK-005 through TASK-016 governance semantics are preserved and
  reused rather than duplicated.
- Exact changed-file scope is automatically enforced, reducing the risk of
  unintended side effects from a worker run.
- The bounded auto artifact provides durable, machine-readable evidence for
  controller review without leaking task bodies, transcripts, secrets, or
  customer data.
- Kimi Swarm can be used as the implementation worker without granting it
  controller, publication, or deployment authority.

## Rejected alternatives

- **Use `kimi --auto` or `--yolo` for swarm execution** — rejected because those
  are permission-bypass modes that would weaken governance. The adapter uses only
  the documented `kimi --prompt` boundary.
- **Invent a non-existent `kimi swarm` subcommand or flag** — rejected after
  inspecting `kimi --help` locally; no such documented capability exists.
- **Allow auto mode without an explicit changed-file scope** — rejected because
  exact scope enforcement is a core safety control of TASK-017.
- **Run staging/commit/push automatically on success** — explicitly out of scope;
  publication remains separately gated by controller/owner approval.
- **Implement automatic iterative repair loops** — rejected as a future task;
  TASK-017 stops and reports on failure rather than autonomously retrying.
