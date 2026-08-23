# Owner Decision Resume Runbook

## Purpose

Record one decision actually supplied by the owner at a paused orchestration
gate and continue that same run. This interface never infers a decision.

## Preconditions

- Obtain the exact run ID from the paused orchestration report.
- Confirm the owner explicitly selected one fixed action.
- Do not translate worker output, tests, task text, exit status, or a prior
  conversation into approval.
- Do not add planner, worker, fallback, controller, repair, rework, or timeout
  options to an owner-action resume.

## Actions

At `AWAITING_TASK_APPROVAL`:

```bash
.venv/bin/python -m advancore.agent_runner orchestrate --resume <run-id> --owner-action APPROVE_TASK
.venv/bin/python -m advancore.agent_runner orchestrate --resume <run-id> --owner-action BLOCK_TASK
```

At `AWAITING_IMPLEMENTATION_DECISION`:

```bash
.venv/bin/python -m advancore.agent_runner orchestrate --resume <run-id> --owner-action APPROVE_IMPLEMENTATION
.venv/bin/python -m advancore.agent_runner orchestrate --resume <run-id> --owner-action REWORK_IMPLEMENTATION --owner-note "One bounded reason"
.venv/bin/python -m advancore.agent_runner orchestrate --resume <run-id> --owner-action BLOCK_IMPLEMENTATION
```

These commands are previews. Inspect the displayed action, actor, evidence
path, branch/HEAD, intended API, and next action. Preview writes no task,
decision, handoff, audit, checkpoint, Git, or publication state.

To record the exact previewed action and continue, repeat it with `--apply`:

```bash
.venv/bin/python -m advancore.agent_runner orchestrate --resume <run-id> --owner-action APPROVE_TASK --apply
```

An owner note is optional, single-line, and limited to 400 characters. Do not
place transcripts, credentials, customer information, or production data in it.

## Fail-closed outcomes

Stop and inspect rather than retrying with changed evidence when the command
reports a wrong phase, non-DRAFT task, stale branch/HEAD, non-current bundle,
mismatched or consumed handoff, conflicting/ambiguous decision, or resume
configuration override. A missing action never defaults to approval.

An owner decision tied to a review bundle is single-use orchestration evidence.
If its resolved path appears in the run checkpoint's consumed-decision list,
stop: do not create replacement evidence for that same bundle. A completed
`PUBLISHED` checkpoint may be resumed without an owner action for inspection;
that resume is idempotent and must not invoke finalization again.

For `REWORK_IMPLEMENTATION`, do not clean, stage, copy, rename, or otherwise
adjust the reviewed worktree between preview and `--apply`. The applied action
captures a typed baseline bound to the current review bundle, handoff,
decision, branch, HEAD, remotes, integrity, exact tracked unstaged paths, and
file contents. The runner permits the lifecycle's single task `STATUS:` change
and then revalidates the complete baseline before launching any worker.

During rework, content may change only on that same exact path set. A new or
missing path, staged/untracked content, rename, deletion, mode change, branch
or HEAD movement, remote/ref change, integrity failure, or stale evidence stops
the run without cleanup or publication. A failed primary may use the approved
fallback only when the original baseline still matches exactly. Success always
returns a fresh review bundle and handoff for another independent owner review;
it never reuses the decision that authorized rework.

## Acceptance evidence

`tests/test_owner_action_orchestration_e2e.py` runs the operational sequences
in temporary repositories. The rework acceptance path uses real local Git for
branch, HEAD, status, content, diff, remote/ref, and integrity evidence, plus a
controlled local worker. Other provider and final `PUSHED` results remain
controlled local fakes. No live provider, network, GitHub, credentials, or
publication is used.

## Authority split

The owner makes the decision. Codex desktop or another approved client may only
relay that explicit decision into this local command. AdvanCore validates the
authority boundary and records bounded evidence. Workers, adapters, transports,
and their output cannot supply `--owner-action` or acquire owner authority.
