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

## Authority split

The owner makes the decision. Codex desktop or another approved client may only
relay that explicit decision into this local command. AdvanCore validates the
authority boundary and records bounded evidence. Workers, adapters, transports,
and their output cannot supply `--owner-action` or acquire owner authority.
