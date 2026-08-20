# Local Agent Runner Architecture

**Date:** 2026-08-20  
**Branch:** `agent-control-foundation`  
**Task:** TASK-005 — Local Agent Runner / Orchestrator Foundation

---

## 1. Purpose

This document describes the first local agent runner for AdvanCore. The runner
is a small orchestration control plane that discovers approved tasks, validates
safety preconditions, builds a canonical worker instruction, and invokes a
replaceable worker adapter. It is explicitly **not** a general autonomous
computer-control agent.

The runner's design priority is safety over convenience: if a precondition is
not met, the runner stops and reports rather than guessing, repairing, forcing,
resetting, merging, or broadening scope.

---

## 2. High-level flow

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   CLI / API     │────▶│  Task discovery  │────▶│  Git inspection │
│  (plan/execute) │     │  (tasks/*.md)    │     │ (read-only)     │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                                                        │
                        ┌──────────────────┐           ▼
                        │  Worker adapter  │◀────┌──────────────┐
                        │  (Kimi / dry-run)│     │  Validation  │
                        └──────────────────┘     └──────────────┘
                                │
                                ▼
                        ┌──────────────────┐
                        │  RunnerResult    │
                        │  + approval gate │
                        └──────────────────┘
```

---

## 3. Modules

| Module | Responsibility |
|--------|---------------|
| `advancore/agent_runner/task.py` | Task-file discovery, parsing, and deterministic selection by ID or path. |
| `advancore/agent_runner/git_info.py` | Safe, read-only Git introspection: repo root, current branch, working-tree cleanliness. |
| `advancore/agent_runner/validation.py` | Fail-closed safety validation: branch, working tree, task status. |
| `advancore/agent_runner/worker.py` | Worker adapter interface, Kimi adapter, dry-run adapter, and canonical instruction builder. |
| `advancore/agent_runner/runner.py` | Orchestration: `plan()` (dry-run) and `execute()` (opt-in worker launch). |
| `advancore/agent_runner/__main__.py` | CLI entry point: `python -m advancore.agent_runner plan TASK-005`. |

---

## 4. Safety model

### Mandatory principles

1. **Dry-run first.** The default `plan` command does not launch a worker or
   modify Git state.
2. **Never operate on `main`.** Execution on `main` stops with a clear error.
3. **Clean working tree required.** Uncommitted changes block launch planning
   and execution.
4. **Only `READY` / `REWORK` tasks are executable.** All other statuses stop.
5. **One bounded task at a time.** The runner selects exactly the requested
   task; it never silently combine multiple READY tasks.
6. **No autonomous merge to `main`.** No merge command is implemented.
7. **No destructive Git commands.** No automatic reset, forced checkout,
   force-push, branch deletion, or history rewrite.
8. **No secrets.** The runner does not read, print, log, or commit `.env`,
   tokens, or credentials.
9. **No production/destructive DB actions.** The runner does not run database
   drops/resets or production migrations.
10. **No self-approval.** Worker completion and passing tests do not equal
    review acceptance.
11. **High-impact actions remain gated.** Commit, push, merge, deployment,
    destructive operations, secrets access, and compliance/commercial rule
    changes require explicit approval.
12. **Fail closed.** Unknown state or unsupported worker behaviour stops and
    reports.

### Validation outcomes

A `ValidationResult` is truthy only when:

- current branch is not `main`,
- working tree is clean,
- task status is in `{READY, REWORK}`.

Any failure produces a clear message and the runner stops before launching the
worker.

---

## 5. Worker adapter boundary

The `WorkerAdapter` abstract class decouples orchestration from the concrete
coding worker:

```python
class WorkerAdapter(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def build_command(self, instruction: str, working_dir: Path) -> list[str]: ...

    @abstractmethod
    def run(self, instruction: str, working_dir: Path) -> WorkerResult: ...
```

### Adapters

- `DryRunWorkerAdapter` — default adapter; never launches a process. Returns
  success so the runner can produce a complete plan without side effects.
- `KimiWorkerAdapter` — invokes the local Kimi Code CLI with
  `kimi --prompt <instruction>`. This is a documented, non-interactive,
  single-prompt invocation mode. Autonomous flags such as `--auto` or `--yolo`
  are intentionally not used.

Future workers can be added by implementing `WorkerAdapter`.

---

## 6. Canonical worker instruction

For task `tasks/TASK-005-local-agent-runner-foundation.md` the runner generates:

```text
Read AGENTS.md.

Execute tasks/TASK-005-local-agent-runner-foundation.md completely.

Do not commit or push until explicitly approved.

Stop with the completion report and git status.
```

The instruction:
- references `AGENTS.md` so the worker reads the constitution first,
- references exactly one task file so the worker loads the approved scope from
  GitHub/source of truth,
- includes the no-commit/no-push gate,
- asks for a completion report and git status,
- does **not** embed the full task specification in the prompt.

---

## 7. CLI usage

Dry-run plan (default):

```bash
.venv/bin/python -m advancore.agent_runner plan TASK-005
```

Opt-in worker execution:

```bash
.venv/bin/python -m advancore.agent_runner plan TASK-005 --execute --worker kimi
```

The `--execute` flag and `--worker kimi` are required to launch Kimi. Without
them the runner only inspects and plans.

---

## 8. Runner state model

`RunnerStatus` enumerates the possible lifecycle states:

- `DISCOVERED` — task found.
- `VALIDATED` — safety checks passed.
- `PLANNING` — plan generated, worker not launched.
- `WORKER_LAUNCHED` — worker process started.
- `WORKER_COMPLETED` — worker finished successfully.
- `WORKER_FAILED` — worker returned an error.
- `AWAITING_APPROVAL` — worker completed; results await owner/reviewer approval.
- `FAILED` — validation or discovery failed.

A `RunnerResult` carries the task, Git snapshot, validation, worker instruction,
worker result, and human-readable messages. This makes every invocation
auditable and easy to test.

---

## 9. Testing approach

- Task parsing, status gating, branch gating, and working-tree gating are
  tested with temporary task files.
- Git interactions are mocked so tests do not depend on the real repository
  state.
- Worker adapters are tested with fakes and with the dry-run adapter.
- The Kimi adapter is verified to build a safe command and to fail gracefully
  when the executable is missing; it is not invoked during tests.
- CLI tests patch `get_git_info` directly and verify exit codes.

---

## 10. Threat / safety boundaries

| Threat | Mitigation |
|--------|-----------|
| Accidental commit/push | Worker instruction forbids it; runner has no commit/push/merge commands. |
| Running on `main` | Validation rejects `main` branch. |
| Dirty-tree surprises | Validation requires a clean working tree. |
| Wrong task executed | Task is selected deterministically by ID/path; ambiguous matches fail. |
| Secret leakage | Runner never reads `.env` or credentials; no secrets in logs. |
| Production DB changes | Runner never runs migrations or destructive DB commands. |
| Unattended autonomous mode | `--auto` / `--yolo` Kimi flags are not used. |
| Hard-coded worker coupling | `WorkerAdapter` interface lets Kimi be replaced later. |

---

## 11. Future extension points

- Additional `WorkerAdapter` implementations for other local or remote workers.
- A `tasks/` status update helper behind an explicit approval gate.
- Integration with GitHub Issues/PRs for task discovery (read-only first).
- Background/scheduled execution only after explicit policy tasks define it.
- Approval-gate state persistence once an auditable store is approved.

---

## 12. Reasoning labels

### FACT

- The runner package lives under `advancore/agent_runner/`.
- The default command is dry-run; worker execution requires `--execute`.
- `main` branch and dirty working trees are rejected.
- Only `READY` and `REWORK` task statuses are executable.
- Kimi Code supports `kimi --prompt <instruction>` for non-interactive prompts.

### ASSUMPTION

- Future tasks will define the next approval gates before commit/push become
  automated.
- Kimi Code's `--prompt` mode remains a suitable bounded invocation.

### INFERENCE

- Keeping the runner local, explicit, and fail-closed lets Alex safely delegate
  routine implementation work while retaining control over high-impact actions.
