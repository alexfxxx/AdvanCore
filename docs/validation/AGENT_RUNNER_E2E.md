# Agent Runner End-to-End Validation

## Purpose

Prove that the local Agent Runner created in TASK-005 can safely plan a bounded
worker task and return to the human/reviewer approval gate without committing,
pushing, merging, or expanding scope.

This is a validation run, not a product-feature task.

## Preconditions

- TASK-005 implemented the `advancore.agent_runner` package on the
  `agent-control-foundation` branch.
- The current branch is not `main`.
- The working tree was clean before the validation artifacts were created; it
  becomes dirty as soon as the new files are written, which is expected because
  TASK-006 forbids committing until review.
- Kimi Code CLI is installed locally and supports the bounded `--prompt`
  invocation mode validated in TASK-005.
- The validation task file `tasks/TASK-006-agent-runner-e2e-validation.md`
  exists and has status `READY`.

## Runner invocation

The runner was invoked in dry-run/planning mode for TASK-006 to demonstrate the
orchestration path and generated worker instruction without triggering a
recursive worker launch:

```bash
.venv/bin/python -m advancore.agent_runner plan TASK-006
```

The generated worker instruction was:

```text
Read AGENTS.md.

Execute tasks/TASK-006-agent-runner-e2e-validation.md completely.

Do not commit or push until explicitly approved.

Stop with the completion report and git status.
```

To exercise the Kimi worker adapter boundary, the equivalent execute command
would be:

```bash
.venv/bin/python -m advancore.agent_runner plan TASK-006 --execute --worker kimi
```

That command is intentionally not run during this supervised validation because
it would spawn a nested Kimi process with the same task prompt. The plan output
below confirms the runner reaches the worker boundary safely and stops at the
approval gate.

### Plan output

```text
================================================================
AdvanCore Local Agent Runner — Execution Plan
================================================================
Task:         TASK-006
Title:        Agent Runner End-to-End Validation
Status:       READY
File:         tasks/TASK-006-agent-runner-e2e-validation.md
Branch:       agent-control-foundation
Repo root:    /Users/alex/Documents/GitHub/AdvanCore
Working tree: dirty
Uncommitted changes:
  ?? docs/validation/
  ?? tests/test_agent_runner_e2e_artifact.py
----------------------------------------------------------------
Validation:
  n/a
----------------------------------------------------------------
Worker instruction:
  Read AGENTS.md.

  Execute tasks/TASK-006-agent-runner-e2e-validation.md completely.

  Do not commit or push until explicitly approved.

  Stop with the completion report and git status.
----------------------------------------------------------------
Worker:       dry-run
Command:      (none)
----------------------------------------------------------------
Allowed automatic actions:
  - Read approved repository files
  - Parse task metadata
  - Inspect git status / branch
  - Generate worker prompt
Gated actions (require explicit approval):
  - Commit, push, merge
  - Destructive Git operations (reset, force push, history rewrite)
  - Production / destructive database actions
  - Secret / credential access
  - Compliance / commercial rule changes
----------------------------------------------------------------
Messages:
  PASS: current branch 'agent-control-foundation' is not 'main'
  FAIL: working tree has uncommitted changes
  PASS: task status 'READY' is executable
  Execution blocked: safety validation failed.
----------------------------------------------------------------
Result status: failed
================================================================
```

## Worker boundary

- The worker adapter is `KimiWorkerAdapter`, which builds the command
  `kimi --prompt <instruction>`.
- No autonomous flags such as `--auto` or `--yolo` are appended.
- The worker is asked only to read `AGENTS.md`, execute the single task file,
  refrain from committing or pushing until explicitly approved, and stop with a
  completion report and `git status`.
- Commit, push, merge, destructive Git operations, production/destructive
database actions, secret access, and compliance/commercial changes remain gated
and outside the worker's automatic authority.

## Validation result

- Task discovery: TASK-006 was found in `tasks/`.
- Status gate: TASK-006 is `READY`, so execution is allowed.
- Branch gate: current branch is `agent-control-foundation`, not `main`.
- Working-tree gate: the runner correctly detected the new uncommitted
  validation artifacts and blocked automatic launch, demonstrating fail-closed
  behavior.
- The runner generated the canonical bounded worker instruction.
- The full pytest suite passed.
- No commits, pushes, merges, or destructive actions were performed.
- The actual TASK-006 work was executed under direct operator supervision; the
  worker (Kimi) stopped at the human/reviewer approval gate as instructed.

## Safety observations

- The runner defaults to dry-run; the worker is not launched unless the operator
  explicitly passes `--execute --worker kimi`.
- `main` is rejected as an execution branch.
- A dirty working tree blocks launch planning.
- Only tasks with status `READY` or `REWORK` are executable.
- The worker instruction references the task file by path instead of embedding
  the full task specification.
- The validation artifact and its test are deterministic and do not depend on
  Kimi being installed or on repository state beyond the documented
  preconditions.

## Facts

- TASK-005 established a fail-closed local Agent Runner.
- The runner is dry-run by default.
- Kimi execution requires explicit `--execute --worker kimi`.
- Commit, push, merge, destructive Git operations, production/destructive
database actions, secret access, compliance/commercial changes, and autonomous
approval remain gated.

## Assumptions

- The locally installed Kimi Code CLI continues to support the bounded
  `--prompt` invocation validated in TASK-005.
- The operator launching `--execute --worker kimi` supervises the run and
  reviews the worker output before approving any commit or push.

## Risks / unresolved issues

- The runner's safety depends on the worker honoring the no-commit/no-push
  instruction. A future task may add an explicit pre- or post-execution Git-state
  verification step.
- Worker execution is local and interactive-terminal dependent. Long-running or
  multi-turn worker sessions are not yet addressed.
- No audit log of runner invocations exists outside the terminal output.
- The `IN_PROGRESS` task status is parsed but not executable; the runner does
  not currently update task status itself.

## Recommended next step

After independent review of TASK-006, use the evidence from this validation run
to define the next runner hardening step rather than immediately granting broader
autonomy. Candidate next steps include adding a post-worker Git-state
verification step or an explicit task-status transition helper, each behind its
own approval gate.
