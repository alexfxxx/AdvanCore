# Local Agent Runner Architecture

**Date:** 2026-08-20  
**Branch:** `agent-control-foundation`  
**Task:** TASK-005 / TASK-007 — Local Agent Runner / Orchestrator Foundation and Post-Worker Verification

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
│  (plan/execute) │     │  (tasks/*.md)    │     │ (pre, read-only)│
└─────────────────┘     └──────────────────┘     └─────────────────┘
                                                        │
                        ┌──────────────────┐           ▼
                        │  Worker adapter  │◀────┌──────────────┐
                        │  (Kimi / dry-run)│     │  Validation  │
                        └──────────────────┘     └──────────────┘
                                │
                                ▼
                        ┌──────────────────┐
                        │ Post-worker Git  │
                        │   inspection     │
                        └──────────────────┘
                                │
                                ▼
                        ┌──────────────────┐     ┌──────────────┐
                        │  RunnerResult    │────▶│ Local audit  │
                        │  + approval gate │     │  (.jsonl)    │
                        └──────────────────┘     └──────────────┘
                                │
                                ▼
                        ┌──────────────────┐
                        │  Review bundle   │
                        │  (.agent_runner/ │
                        │     review/)     │
                        └──────────────────┘
```

---

## 3. Modules

| Module | Responsibility |
|--------|---------------|
| `advancore/agent_runner/task.py` | Task-file discovery, parsing, and deterministic selection by ID or path. |
| `advancore/agent_runner/git_info.py` | Safe, read-only Git introspection: repo root, current branch, HEAD SHA, working-tree cleanliness. |
| `advancore/agent_runner/validation.py` | Fail-closed pre-flight validation: branch, working tree, task status. |
| `advancore/agent_runner/worker.py` | Worker adapter interface, Kimi adapter, dry-run adapter, and canonical instruction builder. |
| `advancore/agent_runner/runner.py` | Orchestration, post-worker verification, and `plan()` / `execute()` entry points. |
| `advancore/agent_runner/audit.py` | Durable local JSON Lines audit records under `.agent_runner/audit/`. |
| `advancore/agent_runner/review_bundle.py` | Controller review bundle model, serializer, builder, writer, loader, and inspection formatter. |
| `advancore/agent_runner/lifecycle.py` | Task-status enum, actor-role enum, transition matrix, and authority-aware status update helper. |
| `advancore/agent_runner/__main__.py` | CLI entry point: `python -m advancore.agent_runner plan TASK-005`, `transition TASK-009 --to ...`, or `review-bundle show`. |

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
13. **Explicit, authority-aware task lifecycle changes.** Task status transitions
    are validated against the state machine and actor role. The default
    `transition` command is preview-only; `--apply` is required to mutate the
    task file, and only the `STATUS:` line is changed.

### Validation outcomes

A `ValidationResult` is truthy only when:

- current branch is not `main`,
- working tree is clean,
- task status is in `{READY, REWORK}`.

Any failure produces a clear message and the runner stops before launching the
worker. `execute()` additionally captures a pre-worker Git snapshot (branch and
HEAD SHA) so the runner can verify repository state independently after the
worker exits.

### Post-worker verification

After the worker exits, `execute()` captures a second Git snapshot and compares
it to the pre-worker snapshot. Approval is blocked unless:

- the branch is unchanged,
- the branch is not `main`,
- the HEAD SHA is unchanged.

Changed paths are surfaced clearly. Worker success is never allowed to override
a failed repository-safety check.

### Local audit records

Every `plan()` and `execute()` invocation appends one JSON Lines record to
`.agent_runner/audit/runner.jsonl`. The record contains only safe metadata:
timestamp, task ID/filename, mode, worker type, branch, pre/post HEAD, pre-flight
validation result, worker result, post-worker verification result, final status,
and changed paths. No credentials, environment dumps, full task bodies, or
worker transcripts are stored. Audit-write failures are reported explicitly.

### Controller review bundles

After every `execute()` invocation that reaches post-worker verification, the
runner writes a deterministic, machine-readable JSON review bundle under
`.agent_runner/review/`. The bundle is designed for independent controller/reviewer
handoff and contains only bounded review metadata:

- timestamp,
- task ID and filename,
- task lifecycle status when available,
- branch, pre-worker HEAD, and post-worker HEAD,
- runner final status,
- worker type and worker success,
- post-worker verification result and messages,
- exact changed paths,
- concise diff summary/statistics,
- audit-record reference,
- recommended controller action.

The recommended action is derived from runner evidence only and may be one of:

- `REVIEW` — worker succeeded and post-worker verification passed.
- `REWORK` — worker failed but repository verification remained safe.
- `BLOCKED` — repository safety verification failed or review evidence could not
  be produced reliably.

The bundle must never recommend or assert `APPROVED`. It also excludes
credentials, environment dumps, connection strings, the full task body, full
worker transcripts, customer/business data, and arbitrary command output.
Bundle-write failures are reported explicitly and do not silently disappear.

Inspect a bundle with:

```bash
.venv/bin/python -m advancore.agent_runner review-bundle show
.venv/bin/python -m advancore.agent_runner review-bundle show path/to/bundle.json
```

The `show` command is read-only and never mutates repository state.

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

Task lifecycle transition (dry-run preview by default):

```bash
.venv/bin/python -m advancore.agent_runner transition TASK-009 --to IN_PROGRESS --actor worker
```

Apply the transition explicitly:

```bash
.venv/bin/python -m advancore.agent_runner transition TASK-009 --to IN_PROGRESS --actor worker --apply
```

Inspect the latest review bundle:

```bash
.venv/bin/python -m advancore.agent_runner review-bundle show
```

Inspect a specific review bundle:

```bash
.venv/bin/python -m advancore.agent_runner review-bundle show .agent_runner/review/20260820T120000_TASK-010.json
```

---

## 8. Task lifecycle state model

`TaskStatus` enumerates the authoritative task statuses:

- `DRAFT` — requirement is incomplete.
- `READY` — approved for implementation.
- `IN_PROGRESS` — actively being worked.
- `REVIEW` — implementation completed and awaiting review.
- `REWORK` — changes requested after review.
- `APPROVED` — accepted for merge/release.
- `BLOCKED` — cannot proceed without a decision or dependency.

Allowed transitions and authority:

| Transition | Authorized roles |
|------------|-----------------|
| DRAFT → READY | controller, owner |
| READY → IN_PROGRESS | worker, owner |
| IN_PROGRESS → REVIEW | worker, owner |
| REVIEW → APPROVED | controller, owner |
| REVIEW → REWORK | controller, owner |
| REWORK → IN_PROGRESS | worker, owner |
| any non-final working state → BLOCKED | controller, owner |
| BLOCKED → READY / REWORK | controller, owner |

`ActorRole` distinguishes:

- `worker` — may request/report work transitions only; cannot approve or block.
- `controller` — controller/reviewer authority; may approve, request rework, and
  manage BLOCKED states.
- `owner` — includes controller/reviewer authority and remains required for
  higher-impact decisions gated elsewhere.

`is_transition_allowed()` is a pure validation function used by the CLI and
`transition_task()` helper. `transition_task()` validates the current status,
checks authority, and previews or applies only the single `STATUS:` line. Every
attempt is recorded in the local audit trail with safe metadata only.

## 9. Runner state model

`RunnerStatus` enumerates the possible lifecycle states:

- `DISCOVERED` — task found.
- `VALIDATED` — safety checks passed.
- `PLANNING` — plan generated, worker not launched.
- `WORKER_LAUNCHED` — worker process started.
- `WORKER_COMPLETED` — worker finished successfully.
- `WORKER_FAILED` — worker returned an error.
- `POST_WORKER_VERIFICATION_FAILED` — worker ran but repository state changed unexpectedly.
- `AWAITING_APPROVAL` — worker completed and repository verification passed; results await owner/reviewer approval.
- `FAILED` — validation or discovery failed.

A `RunnerResult` carries the task, pre- and post-worker Git snapshots,
validation, worker instruction, worker result, post-worker verification, audit
path/write status, and human-readable messages. This makes every invocation
auditable and easy to test.

---

## 10. Testing approach

- Task parsing, status gating, branch gating, and working-tree gating are
  tested with temporary task files.
- Git interactions are mocked so tests do not depend on the real repository
  state.
- Worker adapters are tested with fakes and with the dry-run adapter.
- The Kimi adapter is verified to build a safe command and to fail gracefully
  when the executable is missing; it is not invoked during tests.
- Post-worker verification is tested for unchanged state, HEAD movement,
  branch movement, and changed-path surfacing.
- Audit records are tested for creation, safe field coverage, exclusion of
  sensitive content, and explicit write-failure reporting.
- Review bundles are tested for controller-action rules, safe-field policy,
  changed-path capture, serialization round-trip, read-only inspection, and
  explicit write-failure reporting.
- Lifecycle transitions are tested for allowed/denied authority, dry-run
  behaviour, applied mutation, malformed-file rejection, and audit metadata.
- CLI tests patch `get_git_info` directly and verify exit codes.

---

## 11. Threat / safety boundaries

| Threat | Mitigation |
|--------|-----------|
| Accidental commit/push | Worker instruction forbids it; runner has no commit/push/merge commands. |
| Running on `main` | Validation rejects `main` branch; post-worker verification rejects `main`. |
| Dirty-tree surprises | Validation requires a clean working tree. |
| Unexpected branch/HEAD movement | Post-worker verification fails closed and blocks approval. |
| Wrong task executed | Task is selected deterministically by ID/path; ambiguous matches fail. |
| Secret leakage | Runner never reads `.env` or credentials; audit stores only safe metadata. |
| Production DB changes | Runner never runs migrations or destructive DB commands. |
| Unattended autonomous mode | `--auto` / `--yolo` Kimi flags are not used. |
| Hard-coded worker coupling | `WorkerAdapter` interface lets Kimi be replaced later. |
| Silent audit failure | Audit-write errors are reported explicitly in runner output. |
| Scattered review evidence | One deterministic review bundle per execute run consolidates task identity, Git snapshots, verification result, changed paths, and recommended action. |
| Review bundle contains secrets or full transcripts | Bundle excludes credentials, env dumps, full task body, worker stdout/stderr, and customer data. |
| Worker self-approval through bundle | Bundle recommends only `REVIEW`, `REWORK`, or `BLOCKED`; `APPROVED` is never emitted. |
| Unauthorized task-status changes | `transition` validates state machine and actor role; default is preview-only and `--apply` is required. |

---

## 12. Future extension points

- Additional `WorkerAdapter` implementations for other local or remote workers.
- Integration with GitHub Issues/PRs for task discovery (read-only first).
- Background/scheduled execution only after explicit policy tasks define it.
- Approval-gate state persistence once an auditable store is approved.
- Optional bundle signing or checksums if tamper-evident handoff is required.

---

## 13. Reasoning labels

### FACT

- The runner package lives under `advancore/agent_runner/`.
- The default command is dry-run; worker execution requires `--execute`.
- `main` branch and dirty working trees are rejected.
- Only `READY` and `REWORK` task statuses are executable.
- Kimi Code supports `kimi --prompt <instruction>` for non-interactive prompts.
- `execute()` captures pre- and post-worker Git snapshots including branch and HEAD SHA.
- Worker success cannot override a failed post-worker repository verification.
- Every `plan()` and `execute()` invocation writes a JSON Lines audit record under `.agent_runner/audit/`.
- Task lifecycle transitions are controlled by `TaskStatus`, `ActorRole`, and an explicit transition matrix.
- The `transition` subcommand defaults to preview; `--apply` is required to rewrite the `STATUS:` line.
- A worker cannot transition `REVIEW -> APPROVED`; controller/reviewer or owner authority is required.
- Every `execute()` invocation that reaches post-worker verification writes a JSON review bundle under `.agent_runner/review/`.
- The review bundle recommends only `REVIEW`, `REWORK`, or `BLOCKED`; it never recommends or asserts `APPROVED`.
- The review bundle excludes credentials, environment dumps, full task bodies, worker transcripts, and customer/business data.

### ASSUMPTION

- Future tasks will define the next approval gates before commit/push become
  automated.
- Kimi Code's `--prompt` mode remains a suitable bounded invocation.

### INFERENCE

- Keeping the runner local, explicit, and fail-closed lets Alex safely delegate
  routine implementation work while retaining control over high-impact actions.
