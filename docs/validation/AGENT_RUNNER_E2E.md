# Agent Runner End-to-End Validation

## Purpose

Prove that the local Agent Runner created in TASK-005 can safely launch Kimi for one bounded task and return to the human/reviewer approval gate without committing, pushing, merging, or expanding scope.

This was a validation run, not a product-feature task.

## Preconditions

- TASK-005 implemented the `advancore.agent_runner` package on the `agent-control-foundation` branch.
- The current branch was not `main`.
- The working tree was clean before execution.
- Kimi Code CLI was installed locally and supported the bounded `--prompt` invocation mode validated in TASK-005.
- `tasks/TASK-006-agent-runner-e2e-validation.md` existed locally with status `READY`.

## Runner invocation

The validation was performed in two stages.

First, planning mode was run:

```bash
.venv/bin/python -m advancore.agent_runner plan TASK-006 --worker kimi
```

The runner discovered TASK-006, verified the branch and clean working tree, confirmed `READY` status, generated the bounded worker instruction, and stopped without launching Kimi.

The generated worker instruction was:

```text
Read AGENTS.md.

Execute tasks/TASK-006-agent-runner-e2e-validation.md completely.

Do not commit or push until explicitly approved.

Stop with the completion report and git status.
```

Second, the actual worker path was executed:

```bash
.venv/bin/python -m advancore.agent_runner plan TASK-006 --worker kimi --execute
```

The Agent Runner launched Kimi itself using the bounded worker instruction. Alex did not manually open Kimi or paste the task prompt into a Kimi session.

Kimi completed TASK-006, created the required validation artifact and test, ran the full pytest suite, and stopped without committing or pushing. The outer Agent Runner process then returned control to the normal shell with exit code `0`.

## Worker boundary

- The worker adapter was `KimiWorkerAdapter`, which builds `kimi --prompt <instruction>` using an argument array.
- No autonomous flags such as `--auto` or `--yolo` were appended.
- The worker was asked only to read `AGENTS.md`, execute the single task file, refrain from committing or pushing until explicitly approved, and stop with a completion report and `git status`.
- Commit, push, merge, destructive Git operations, production/destructive database actions, secret access, and compliance/commercial changes remained gated and outside the runner's automatic authority.

## Validation result

- Task discovery: PASS — TASK-006 was found in `tasks/`.
- Status gate: PASS — TASK-006 was `READY`.
- Branch gate: PASS — current branch was `agent-control-foundation`, not `main`.
- Working-tree gate before execution: PASS — working tree was clean.
- Dry-run planning: PASS — worker instruction was generated and Kimi was not launched.
- Execute path: PASS — the Agent Runner launched Kimi itself with `--execute --worker kimi`.
- Worker implementation: PASS — Kimi created only the bounded TASK-006 artifacts.
- Test suite: PASS — `63 passed`.
- Commit/push gate during worker execution: PASS — Kimi stopped with no commit or push.
- Outer runner completion: PASS — process returned to the normal shell with exit code `0`.
- Human-gated commit/push: PASS — only after review did Alex manually commit and push the three TASK-006 files to `agent-control-foundation`.

The first ChatGPT-to-Kimi relay step was therefore successfully automated:

`GitHub READY task -> Local Agent Runner -> Kimi -> implementation/tests -> human/reviewer gate`

## Safety observations

- The runner defaults to dry-run; worker execution requires explicit `--execute --worker kimi`.
- `main` is rejected as an execution branch.
- A dirty working tree blocks a new worker launch.
- Only tasks with status `READY` or `REWORK` are executable.
- Task-file content is treated as metadata/instructions rather than executable shell code.
- Kimi honored the no-commit/no-push boundary in this supervised run.
- The outer runner's final approval-state presentation was not sufficiently obvious in the captured terminal output. Although the process returned exit code `0`, a future hardening task should make post-worker status and Git-state verification explicit and durable.

## Facts

- TASK-005 established a fail-closed local Agent Runner.
- TASK-006 actually exercised both planning mode and the real Kimi execute path.
- The runner launched Kimi without Alex manually transferring the task prompt.
- Kimi completed the task and `63` tests passed.
- Kimi did not commit or push during worker execution.
- The outer runner returned exit code `0`.
- The subsequent TASK-006 commit/push was performed manually after review.

## Assumptions

- The locally installed Kimi Code CLI continues to support bounded `--prompt` invocation.
- Until stronger technical enforcement is added, Kimi must continue to honor the no-commit/no-push instruction.

## Risks / unresolved issues

- The runner currently depends partly on the worker honoring the no-commit/no-push instruction.
- Post-worker Git state is not yet independently re-verified and surfaced as a first-class approval artifact.
- No persistent audit log of runner invocations exists outside terminal output and repository/task records.
- Final runner state such as `AWAITING_APPROVAL` should be made more explicit in operator-visible output.
- Long-running or multi-turn worker sessions are not yet addressed.
- The runner does not yet retrieve/sync new READY tasks from GitHub automatically.
- Commit/push to the controlled review branch is still manual.

## Recommended next step

Create a bounded runner-hardening task that adds post-worker Git-state verification, a durable local audit record, and explicit approval-state output while keeping commit, push, merge, task-status mutation, production access, secrets, and destructive operations gated.
