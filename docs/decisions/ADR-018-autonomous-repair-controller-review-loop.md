# ADR-018 — Autonomous Repair + Controller Review Loop

## Status

Accepted — implemented as part of TASK-018.

## Context

TASK-017 reduced the manual workflow to a single governed auto-pipeline command:

```bash
.venv/bin/python -m advancore.agent_runner auto TASK-017 --worker kimi-swarm
```

That pipeline still stops and reports on every failed gate. The largest remaining
source of owner time is recoverable failure handling: a failed test, whitespace
error, or safe worker implementation error still requires a human to inspect the
failure and manually re-run Kimi.

The goal of TASK-018 is to automate that repair cycle while preserving the same
governance perimeter: GitHub remains the source of truth, the local AdvanCore
runner remains the enforcement authority, and no automatic staging, commit,
push, merge, deployment, credential access, or controller approval is added.

## Decision

Extend `advancore/agent_runner/auto_pipeline.py` with a bounded autonomous
repair orchestration layer controlled by a new `--repair-attempts N` option on
the `auto` subcommand.

### Repair classification

The runner classifies every failure as either repairable or non-repairable:

- **Repairable:**
  - `TEST_FAILED` — pytest exited non-zero.
  - `DIFF_CHECK_FAILED` — `git diff --check` detected whitespace errors.
  - `WORKER_FAILED` — the worker returned non-zero, but branch/HEAD/staging
    checks are still clean.

- **Non-repairable (fail-closed):**
  - `VALIDATION_FAILED` — branch, working-tree, or task-status gate failed.
  - `POST_WORKER_VERIFICATION_FAILED` — branch or HEAD moved unexpectedly.
  - `SCOPE_FAILED` — missing/unsafe allowed scope or actual changes exceed it.
  - `ARTIFACT_FAILED` — audit/artifact integrity failure where safe continuation
    cannot be proven.
  - Any other ambiguous or unauthorized state.

When repair is enabled, non-repairable failures are reported as
`NON_REPAIRABLE` so the consolidated report makes the escalation clear.

### Repair budget

The repair budget is explicit, deterministic, and small:

- CLI default is `0`, preserving the original TASK-017 single-pass behavior.
- Allowed range is `0-2`.
- Values outside the range are clamped (negative → `0`; above `2` → `2`).

### Repair instruction

For each repair attempt the runner builds a canonical bounded instruction that:

- reuses the existing Kimi Swarm governance boundary,
- restates the task ID, task file, and exact allowed changed-file scope,
- names the triggering gate and attempt number,
- includes only bounded evidence (return codes, short summaries) and never full
  worker transcripts, secrets, environment variables, or arbitrary command
  output,
- explicitly forbids `--auto`, `--yolo`, permission-bypass modes, destructive
  Git operations, staging, commit, push, merge, branch switch, credential
  access, deployment, and self-approval.

The instruction is sent through the same worker adapter selected for the
original attempt (preserving `kimi-swarm` when already chosen).
### Post-repair verification

After every repair attempt the full governed verification sequence reruns:

1. Capture pre/post Git snapshots.
2. Verify branch/HEAD stability.
3. Detect staged/index changes.
4. Run the full pytest suite.
5. Run `git diff --check` (unstaged and staged).
6. Validate exact changed-file scope.
7. Write a bounded auto artifact.

A successful repair ends only at `READY_FOR_APPROVAL`. It does not stage,
commit, push, merge, deploy, or mutate lifecycle state.

### Terminal states

- `READY_FOR_APPROVAL` — all gates passed after the initial run or a repair.
- `REPAIR_EXHAUSTED` — the repair budget was consumed without a passing run.
- `NON_REPAIRABLE` — a governance/safety failure cannot be autonomously
  repaired and requires immediate controller/owner review.

The original TASK-017 statuses (`VALIDATION_FAILED`, `WORKER_FAILED`,
`POST_WORKER_VERIFICATION_FAILED`, `TEST_FAILED`, `DIFF_CHECK_FAILED`,
`SCOPE_FAILED`, `ARTIFACT_FAILED`) are still emitted when repair is disabled.

### Audit artifact

Each pipeline run still appends a bounded JSON Lines record to
`.agent_runner/auto/auto_pipeline.jsonl`. When repair is enabled, the record
also includes:

- `max_repair_attempts`,
- a bounded list of repair attempts with attempt number, triggering gate,
  status, worker type, worker success, verification status, and evidence keys
  only.

Full transcripts, command output, secrets, and environment dumps remain excluded.

## Consequences

- Recoverable implementation/test/diff failures can be retried automatically,
  reducing owner time for routine issues.
- Governance violations and ambiguous states fail closed immediately and are
  escalated to controller/owner review.
- The repair loop never grants controller, publication, or deployment authority
  to Kimi or any swarm/sub-agent.
- The bounded repair instruction and artifact keep the audit trail safe and
  reviewable.
- Default behavior remains unchanged; repair is opt-in and capped.

## Rejected alternatives

- **Unlimited/self-directed repair loops** — rejected because an unbounded loop
  could amplify mistakes and obscure governance failures.
- **Repairing scope failures by deleting out-of-scope files automatically** —
  rejected because file deletion is a destructive operation that requires
  explicit reviewer approval.
- **Repairing branch/HEAD mutations or staged changes** — rejected because these
  are governance violations that must escalate to controller/owner review.
- **Default `--repair-attempts` greater than 0** — rejected to preserve the
  existing TASK-017 single-pass default behavior.
- **Allowing `--repair-attempts` above 2 without owner approval** — rejected to
  keep the autonomous repair budget small and deterministic.
