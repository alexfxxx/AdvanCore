# Governed Worker Fallback Runbook

## Purpose

Use this procedure when an approved implementation task may need one local,
preselected worker fallback. Fallback handles provider availability only; it
does not add implementation scope or approval/publication authority.

## Select the workers

- Choose the primary and fallback from the code-owned worker registry.
- Configure the fallback explicitly and before execution. Omitting
  `--fallback-worker` means no fallback.
- The workers must differ. `dry-run` cannot be paired with a fallback.
- Confirm the task is executable, the current branch is not `main`, the working
  tree is clean, and the task's allowed changed-file scope is exact.

For an approved TASK-023-style Kimi-Swarm to Codex run:

```bash
.venv/bin/python -m advancore.agent_runner auto TASK-023 \
  --worker kimi-swarm --fallback-worker codex
```

The fixed Codex adapter denies interactive approval, uses an ephemeral session
and `workspace-write` sandbox, and does not expose arbitrary argv, cloud mode,
extra writable roots, permission bypass, web search, or credential input.

## Expected behavior and stops

The runner invokes at most the primary plus one configured fallback. It may use
the fallback only when the primary failure is classified as executable missing,
quota/capacity, or authentication unavailable and branch, HEAD, index,
worktree, and remotes are unchanged.

Stop and investigate; do not retry by manually chaining another worker when:

- the failure is unknown;
- branch, HEAD, index, worktree, or remotes changed or cannot be verified;
- the configured fallback fails;
- worker policy is invalid or ambiguous; or
- subsequent verification, scope, artifact, or governance gates fail.
- the worker times out or is cancelled. These are terminal, non-availability
  conditions and never qualify for fallback or autonomous repair.

## Timeout and cancellation recovery

The default worker timeout is 1,800 seconds. A reviewed invocation may set a
canonical integer from 1 through 7,200 seconds with `--worker-timeout`; zero,
negative, signed, decimal, padded, malformed, and excessive values are rejected.
For example:

```bash
.venv/bin/python -m advancore.agent_runner auto TASK-024 \
  --worker codex --worker-timeout 1800
```

After timeout or operator cancellation, confirm the report's terminal reason
and Git-state evidence. If any branch, HEAD, index, worktree, or remote mutation
is reported—or evidence is ambiguous—stop for controller review. If state is
unchanged, the only governed instruction is: `Explicitly resume or start a
separately reviewed worker invocation.` There is no silent retry.

## Review evidence

Review the consolidated report and `.agent_runner/auto/` evidence. Confirm the
task and branch, primary worker, classified primary failure, configured
fallback, terminal worker, repository-integrity result, verification results,
and exact changed paths. These artifacts intentionally contain bounded metadata
and must not contain worker transcripts, environment dumps, credentials, or
secret values.

## Resume and exceptions

For `orchestrate`, resume only with the run ID emitted by the runner:

```bash
.venv/bin/python -m advancore.agent_runner orchestrate \
  --resume <run-id> --apply
```

Resume uses the checkpointed worker/fallback selection and budgets; do not
silently substitute new workers or turn a terminal fallback failure into a
third hop. For the standalone `auto` command, correct the reported exception
and start a separately reviewed invocation; no hidden fallback state is
assumed.

## Continuing authority gates

`agent_runner` permanently owns worker selection policy, fallback eligibility,
Git-integrity validation, bounded evidence, verification, and terminal
reporting. Local clients or operators may launch, monitor, resume, and present
exceptions, but do not replace that control plane.

Passing verification and `READY_FOR_APPROVAL` are evidence, not approval.
Controller review remains independent. TASK-020 finalization requires fresh,
matching controller approval and retains its lifecycle, exact-staging, commit,
and non-`main` push gates. Fallback never stages, commits, pushes, merges,
deploys, changes remotes, or accesses credentials on the runner's behalf.
