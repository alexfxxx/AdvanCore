# Exception-Based Development Loop Runbook

## Purpose and authority

This runbook operates the governed owner-goal-to-feature-branch loop demonstrated by TASK-029. GitHub repository content is the source of truth. Planner output is a proposal; `agent_runner` constructs the task; only an owner/controller decision can resume either gate; implementation workers cannot approve or finalize.

FACT: The automated acceptance uses a temporary repository, controlled fakes, and no remote. It proves delegation and recorded outcome, not live publication.

ASSUMPTION: The operator is in the intended local repository, on the intended non-`main` feature branch, with the project virtual environment available.

## Prerequisites

Before starting, confirm:

- `git branch --show-current` reports a named feature branch, never `main`.
- `git status --short` is empty.
- The goal is bounded and contains no credentials, secrets, production data, or unapproved commercial/compliance rules.
- The requested changed-file scope is explicit.
- The owner understands that two different decisions are required: task approval and implementation approval.

Run the operational acceptance proof with:

```sh
.venv/bin/pytest -q tests/test_exception_development_loop_e2e.py
```

Expected result: `7 passed`. The test creates only temporary local repositories and must not require credentials, a remote, or network access.

## Happy path and checkpoints

Start the applied orchestration with a primary Kimi-Swarm planner and one Codex fallback:

```sh
.venv/bin/python -m advancore.agent_runner orchestrate \
  --goal "<bounded owner goal>" \
  --planner kimi-swarm \
  --fallback-planner codex \
  --worker codex \
  --apply
```

Record the returned run ID. Inspect `.agent_runner/orchestration/<run-id>.json` and the goal-task audit artifact. Under a controlled primary failure, the evidence must identify the Kimi-Swarm attempt, its eligible fallback reason, Codex as the terminal planner, and runner construction of a `STATUS: DRAFT` task under `tasks/`.

Checkpoint 1 is `AWAITING_TASK_APPROVAL`. No worker or finalizer may have run. Review the canonical task, its scope, tests, assumptions, and owner decisions. Do not treat a planner recommendation as approval.

Preview the first owner action:

```sh
.venv/bin/python -m advancore.agent_runner orchestrate \
  --resume <run-id> \
  --owner-action APPROVE_TASK
```

If the preview is correct, the owner may apply the same action:

```sh
.venv/bin/python -m advancore.agent_runner orchestrate \
  --resume <run-id> \
  --owner-action APPROVE_TASK \
  --apply
```

The runner performs `DRAFT -> READY`. For a runner-generated task that is the only changed path, it preserves that approved task specification in one local feature-branch commit. This is the clean-tree source-of-truth handoff: it stages no other path, does not push, does not switch branches, and fails closed on `main`, changed HEAD, or any additional changed file. The bounded Codex worker then runs exactly once, followed by runner-controlled pytest, diff, staging, and changed-scope verification.

Checkpoint 2 is `AWAITING_IMPLEMENTATION_DECISION`. Inspect the review bundle, auto-pipeline artifact, changed paths, test result, worker identity, branch, and pre/post HEAD. Verification success is not approval, and finalization must not yet have run.

Preview and then apply the separate implementation decision:

```sh
.venv/bin/python -m advancore.agent_runner orchestrate \
  --resume <run-id> \
  --owner-action APPROVE_IMPLEMENTATION

.venv/bin/python -m advancore.agent_runner orchestrate \
  --resume <run-id> \
  --owner-action APPROVE_IMPLEMENTATION \
  --apply
```

Only after the second decision may `agent_runner` delegate the established feature-branch finalization boundary. Confirm its evidence is bound to the task, review bundle, feature branch, and expected HEAD. Live push behavior is outside the automated acceptance proof and requires the separately approved operating context.

## Evidence checklist

- Orchestration checkpoint: phase history, run/task identity, branch/HEAD, consumed decision paths.
- Goal-task artifact: primary attempt, fallback classification, integrity evidence, terminal planner.
- Canonical task: runner-assigned task ID and lifecycle state.
- Approved-task commit: exactly the generated task path and no remote publication.
- Auto-pipeline artifact: one bounded worker invocation and verification result.
- Review bundle and handoff: matching task, branch, HEAD, and changed scope.
- Controller decision: owner/controller actor, exact bundle, and unconsumed evidence.
- Finalization artifact: delegation result; never infer approval from a successful worker or transport response.

## Exceptions and safe recovery

- Missing first decision: remain at `AWAITING_TASK_APPROVAL`; review the DRAFT and resume only with an explicit owner action.
- Malformed planner output: stop at task generation. Preserve the failure classification; correct the proposal source or planner selection and start a new governed attempt. Do not hand-author authoritative planner state in a checkpoint.
- Ineligible or mutating planner failure: no fallback is allowed. Inspect repository integrity before any retry.
- Approved-task handoff blocked by dirty tree: do not stage or discard files automatically. Identify every changed path, preserve unrelated owner work, restore an intentionally clean feature-branch state through an approved workflow, then repeat the explicit resume.
- Worker failure: no second-gate decision or finalization. Inspect bounded worker evidence and use the configured repair/rework boundary only if authorized.
- Verification failure: finalization remains blocked. Correct only authorized scope and rerun verification; test success cannot be substituted with a decision.
- Staging/publication attempt by a worker: treat as a scope failure. Inspect the index and audit evidence; do not continue until the unexpected state is safely resolved.
- Missing second decision: remain at `AWAITING_IMPLEMENTATION_DECISION`; verify the current bundle and record a separate decision.
- Stale/conflicting/consumed decision: do not reuse or edit evidence. Resolve the exact bundle/branch/HEAD mismatch and create a new valid controller action where permitted.
- `main`, detached HEAD, changed branch, or changed HEAD: stop. Never switch, reset, rebase, merge, or force-push as an automated recovery.
- Finalization failure: preserve the checkpoint and finalization artifact. Do not claim publication; escalate for owner/controller review.

INFERENCE: A safe resume is possible only when the checkpoint, task, current branch/HEAD, review evidence, and explicit decision still agree. Ambiguity is a blocked state, not permission to reconstruct authority.

PROPOSAL: Before any future live-publication exercise, obtain independent approval for the remote, branch protection, and push verification procedure; TASK-029 does not approve that activity.
