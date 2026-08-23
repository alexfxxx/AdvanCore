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
                                │
                                ▼
                        ┌──────────────────┐
                        │ Controller       │
                        │ handoff request  │
                        │ (.agent_runner/  │
                        │ controller_handoff/)
                        └──────────────────┘
                                │
                                ▼
                        ┌──────────────────┐
                        │ Controller       │
                        │ adapter boundary │
                        │ (manual / future)│
                        └──────────────────┘
                                │
                                ▼
                        ┌──────────────────┐
                        │ Controller       │
                        │ transport        │
                        │ envelope         │
                        │ (.agent_runner/  │
                        │  controller_tran │
                        │      sport)      │
                        └──────────────────┘
                                │
                                ▼
                        ┌──────────────────┐
                        │ Controller       │
                        │ decision record  │
                        │ (.agent_runner/  │
                        │    decisions/)   │
                        └──────────────────┘
                                │
                                ▼
                        ┌──────────────────┐     ┌──────────────┐
                        │ Decision →       │────▶│ Lifecycle    │
                        │ lifecycle bridge │     │ mutation     │
                        │ (preview/apply)  │     │ (STATUS only)│
                        └──────────────────┘     └──────────────┘
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
| `advancore/agent_runner/controller_handoff.py` | Controller handoff request model, prepare/reconcile logic, writer, loader, and inspection formatter. |
| `advancore/agent_runner/controller_decision.py` | Controller decision record model, serializer, builder, writer, loader, and inspection formatter. |
| `advancore/agent_runner/lifecycle.py` | Task-status enum, actor-role enum, transition matrix, and authority-aware status update helper. |
| `advancore/agent_runner/decision_lifecycle_bridge.py` | Fail-closed bridge from a validated controller decision record to the existing task lifecycle; preview by default, explicit `--apply` required to mutate. |
| `advancore/agent_runner/controller_adapter.py` | Replaceable controller-adapter boundary and built-in `manual` adapter; dispatches a handoff request to one adapter and reconciles any returned decision through TASK-013. |
| `advancore/agent_runner/controller_transport.py` | Versioned, transport-neutral controller request/response envelope around the TASK-014 adapter boundary; deterministic serialization, validation, local file round-trip, and response reconciliation delegation. |
| `advancore/agent_runner/controller_transport_driver.py` | Replaceable controller transport-driver contract plus a bounded local-filesystem driver that separates envelope semantics from delivery mechanics. |
| `advancore/agent_runner/__main__.py` | CLI entry point: `python -m advancore.agent_runner plan TASK-005`, `transition TASK-009 --to ...`, `review-bundle show`, `controller-decision record/show/apply`, `controller-handoff prepare/show/reconcile`, `controller-adapter dispatch/status`, or `controller-transport request/show/validate-response/driver-send/driver-receive/driver-show`. |

---

## 4. Safety model

### Explicit owner decision intake and resume (TASK-025)

`orchestrate --resume <run-id> --owner-action <ACTION>` accepts one fixed,
code-owned owner action at an existing approval gate. It does not parse natural
language or allow planners, workers, controller adapters, or transport drivers
to assert owner authority. AdvanCore validates the checkpointed phase, task or
review-bundle linkage, handoff evidence, branch, HEAD, and resume configuration
before it calls an existing governance API.

Task actions are valid only at `AWAITING_TASK_APPROVAL`. `APPROVE_TASK` and
`BLOCK_TASK` call the existing owner lifecycle transition from the checkpointed
`DRAFT` task to `READY` or `BLOCKED`; status text is never edited directly.
Implementation actions are valid only at `AWAITING_IMPLEMENTATION_DECISION`.
They map to the existing `ControllerDecision` values, use actor `owner`, bind to
the current checkpointed bundle and handoff evidence, and then use the existing
handoff reconciliation and orchestration state machine.

Preview is the default and performs no writes. `--apply` durably records the
action and continues the same invocation. Checkpoints and consolidated results
retain only bounded evidence: action, actor, evidence path, preview/applied
state, and one next action. Optional notes are stripped, limited to one line and
400 characters, and stored only in implementation decision records. No
conversation transcript is accepted or persisted.

The authority boundary is explicit: Codex desktop or another approved local
client may invoke the CLI only after the owner actually supplies the decision.
The client relays that explicit choice; permanent AdvanCore code validates and
records it. Missing, inferred, stale, phase-mismatched, conflicting,
duplicate-ambiguous, or consumed actions fail closed. Resume-time provider,
budget, and timeout overrides cannot be combined with owner action intake.

TASK-026 acceptance follows one checkpointed run through both owner gates and
the existing TASK-020 finalizer. Deterministic temporary-repository tests prove
that task, run, review bundle, handoff, branch, and HEAD remain correlated;
previews write nothing; stale, phase-mismatched, conflicting, worker-authored,
consumed, and override evidence fails closed; and a terminal resume cannot
repeat finalization. Publication is represented only by a controlled local
`PUSHED` fake, so the suite has no provider, network, GitHub, credential, or
production-publication dependency.

### Bounded worker lifetime and recovery (TASK-024)

Kimi, Kimi-Swarm, and Codex execute through one code-owned process runner. The
runner uses a 1,800-second default, accepts only canonical positive integer
overrides, and rejects values above 7,200 seconds. Each worker starts in a new
local session. Timeout or keyboard cancellation terminates its whole process
group, waits one bounded graceful second, and then forces termination if needed.

Timeout/cancellation results contain no prompt, stdout, stderr, environment, or
credential material. They record only the terminal reason, timeout policy,
bounded post-termination Git evidence, and—when branch, HEAD, index, worktree,
and remotes are independently unchanged—this exact action:
`Explicitly resume or start a separately reviewed worker invocation.` Mutation
or ambiguous evidence stops for controller review. Neither outcome triggers
fallback, repair, retry, publication, or lifecycle authority. Orchestration
checkpoints retain the original timeout so resume cannot silently replace it.

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
14. **Controller decisions are local records, not actions.** A controller
    decision record carries an independent review decision back into the local
    control plane. It does not perform commit, push, merge, deployment, or
    automatic task transition, and workers cannot create controller decision
    records.
15. **Decision-to-lifecycle bridge is fail-closed and preview-first.** A
    controller decision record may be bridged into the existing lifecycle state
    machine only after all linkage evidence validates. Preview is the default;
    an explicit `--apply` is required to mutate the task file, and only the
    `STATUS:` line is changed. The bridge reuses the existing TASK-009 authority
    model and cannot bypass it.
16. **Controller adapter is a transport boundary, not an authority source.** A
    controller adapter consumes a validated handoff request and returns a bounded
    result. It does not make a worker into a controller, treat a handoff request
    as approval, fabricate an `APPROVE` decision, bypass TASK-011 decision
    validation, bypass TASK-012 lifecycle authority, or mutate task/Git/database
    state. The built-in `manual` adapter performs no network or subprocess
    execution.

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

### Controller handoff requests

After a review bundle is produced, the runner (or a human operator) may prepare a
deterministic, machine-readable handoff request under
`.agent_runner/controller_handoff/`. The request represents “this review bundle
is waiting for an independent controller decision.” It contains only bounded
safe metadata:

- request version and request ID,
- timestamp,
- task ID and filename,
- review-bundle path/reference,
- review-bundle branch and pre/post HEAD evidence,
- review-bundle recommended action,
- handoff state,
- reconciled controller-decision path/value when available,
- audit reference when available.

A handoff request is an orchestration artifact only. It is not controller
approval, owner approval, or permission to commit, push, merge, deploy, mutate
lifecycle state, or impersonate the controller.

The handoff state model is intentionally small:

- `WAITING_DECISION` — a valid review bundle has been prepared for independent
  controller review.
- `DECISION_RECEIVED` — a valid controller decision record has been reconciled
  to the request.
- `BLOCKED` — reserved for missing, malformed, conflicting, or unsafe handoff
  evidence.

Prepare a handoff request from the latest review bundle:

```bash
.venv/bin/python -m advancore.agent_runner controller-handoff prepare
.venv/bin/python -m advancore.agent_runner controller-handoff prepare .agent_runner/review/20260820T120000_TASK-010.json
```

Reconcile a handoff request with a controller decision record:

```bash
.venv/bin/python -m advancore.agent_runner controller-handoff reconcile
.venv/bin/python -m advancore.agent_runner controller-handoff reconcile .agent_runner/controller_handoff/20260821T120000_TASK-013_WAITING_DECISION.json .agent_runner/decisions/20260821T130000_TASK-013_APPROVE.json
```

Inspect the latest handoff request:

```bash
.venv/bin/python -m advancore.agent_runner controller-handoff show
.venv/bin/python -m advancore.agent_runner controller-handoff show .agent_runner/controller_handoff/20260821T120000_TASK-013_WAITING_DECISION.json
```

The `show` command is read-only. `prepare` and `reconcile` write only local
`.agent_runner/` artifacts and do not mutate task files, Git state, or lifecycle
state.

### Controller adapter boundary

The `controller_adapter` module defines a replaceable boundary between the local
handoff queue and an independent controller. A controller adapter consumes a
validated handoff request and returns a bounded adapter result. It is a
transport/orchestration layer, not an authority source.

The adapter result state model is intentionally small:

- `PENDING` — the handoff request is valid but no controller decision has been
  returned yet.
- `DECISION_RECEIVED` — a valid controller decision has been returned or was
  already reconciled to the request.
- `BLOCKED` — adapter execution failed, the returned evidence is missing,
  malformed, inconsistent, unauthorized, or unsafe.

The built-in `manual` adapter is local, read-only, and performs no network or
subprocess execution. It validates the handoff request, exposes bounded handoff
metadata, and returns `PENDING` until a separately valid controller decision
exists. It never infers an `APPROVE` decision from the review-bundle
recommendation.

Dispatching an adapter loads the handoff request, invokes exactly one selected
adapter, validates the returned result state, and—if the adapter reports
`DECISION_RECEIVED` with a decision path—reconciles the decision through the
existing TASK-013 handoff reconciliation logic. It does not invoke the TASK-012
lifecycle bridge and does not mutate task files, Git state, or database state.

`status`/inspection is read-only and does not reconcile decisions or write
artifacts.

### Controller transport envelope

The `controller_transport` module defines a deterministic, bounded,
transport-neutral request/response envelope around the existing TASK-014
controller-adapter boundary. It lets a future remote controller transport
exchange safe artifacts without redesigning controller authority, handoff,
decision, lifecycle, or Git-publication semantics.

A request envelope carries only bounded safe metadata:

- envelope version and schema;
- unique transport correlation/request ID;
- task identity (ID and filename);
- source handoff-request path and ID;
- linked review-bundle path;
- target controller adapter name and optional adapter type;
- bounded bundle evidence (branch, pre/post HEAD, recommended action, handoff state);
- created timestamp.

A response envelope carries only bounded safe metadata:

- envelope version and schema;
- matching correlation/request ID;
- task identity;
- source handoff-request path and linked review-bundle path;
- result state limited to `PENDING`, `DECISION_RECEIVED`, or `BLOCKED`;
- optional controller-decision record reference/path and decision value;
- bounded failure/blocking messages.

The envelope is data exchange only. It is not controller authority: it does not
make a worker a controller, infer `APPROVE`, treat `DECISION_RECEIVED` as
sufficient authority without a separately valid TASK-011 decision record, or
bypass TASK-012 lifecycle authority or TASK-013 handoff reconciliation.

Serialization is deterministic JSON with sorted keys. The module provides:

- `build_transport_request()` / `handoff_to_transport_request()` — convert a
  validated handoff request into a transport request envelope.
- `write_transport_request()` / `load_transport_request()` — local file round-trip.
- `build_transport_response()` — build a response envelope from a request and
  result state.
- `write_transport_response()` / `load_transport_response()` — local file round-trip.
- `validate_transport_request()` / `validate_transport_response()` — fail-closed
  schema, version, required-field, and correlation/reference validation.
- `convert_response_to_adapter_result()` — pure conversion to a bounded
  TASK-014 adapter result.
- `apply_transport_response()` — validate a response envelope and, if it reports
  `DECISION_RECEIVED` with a decision path, reconcile the decision through the
  existing TASK-013 `reconcile_controller_handoff()` logic.

Local envelope artifacts are stored under `.agent_runner/controller_transport/`
and gitignored through the existing `.agent_runner/` rule. Envelope operations
write only local artifacts and audit metadata; they do not mutate task files,
Git state, lifecycle state, or database state.

Create a transport request envelope from the latest handoff request:

```bash
.venv/bin/python -m advancore.agent_runner controller-transport request
.venv/bin/python -m advancore.agent_runner controller-transport request .agent_runner/controller_handoff/20260821T120000_TASK-015_WAITING_DECISION.json --adapter manual
```

Inspect a transport envelope (read-only):

```bash
.venv/bin/python -m advancore.agent_runner controller-transport show
.venv/bin/python -m advancore.agent_runner controller-transport show .agent_runner/controller_transport/20260821T120000_TASK-015_CTE-xxxx_request.json
```

Validate a transport response envelope and reconcile any returned decision:

```bash
.venv/bin/python -m advancore.agent_runner controller-transport validate-response
.venv/bin/python -m advancore.agent_runner controller-transport validate-response .agent_runner/controller_transport/20260821T130000_TASK-015_CTE-xxxx_response.json
```

### Controller transport-driver boundary

The `controller_transport_driver` module adds a small, replaceable transport-driver
contract around the TASK-015 envelope. It separates envelope semantics from
delivery mechanics so that a future remote transport can be added without changing
controller authority, handoff reconciliation, lifecycle authority, or
Git-publication governance.

The driver contract is intentionally minimal:

- `send(request)` writes a validated TASK-015 request envelope to the transport
  store and returns the artifact path.
- `receive(request)` loads the single TASK-015 response envelope bound to a
  request, validating it against the expected correlation ID, task ID, handoff
  path, and review-bundle path.
- `show(request_id)` inspects driver artifacts for a correlation ID without
  mutation.

The built-in `LocalFilesystemTransportDriver` uses two bounded directories under
`.agent_runner/controller_transport/`:

- `outbox/` for request envelopes.
- `inbox/` for response envelopes.

It is local-filesystem only: no HTTP, webhooks, sockets, queues, background
polling, model calls, credentials, or subprocess transport. It is deterministic
and idempotent for identical requests, fails closed on conflicting duplicates,
missing/ambiguous responses, malformed files, unknown schema/version/state, or
reference mismatches, and rejects path traversal or symlink escape outside the
bounded directories.

The driver is delivery plumbing only. It does not create, infer, approve,
reconcile, apply, publish, or deploy. A returned `DECISION_RECEIVED` response is
still only evidence of a returned decision; it must flow through the existing
TASK-011/TASK-013/TASK-014/TASK-015 validation/reconciliation helpers before any
lifecycle action is considered.

Send a transport request envelope through the local driver:

```bash
.venv/bin/python -m advancore.agent_runner controller-transport driver-send
.venv/bin/python -m advancore.agent_runner controller-transport driver-send .agent_runner/controller_handoff/20260821T120000_TASK-016_WAITING_DECISION.json
```

Receive a transport response envelope through the local driver:

```bash
.venv/bin/python -m advancore.agent_runner controller-transport driver-receive
.venv/bin/python -m advancore.agent_runner controller-transport driver-receive CTE-xxxx
```

Show local driver artifacts for a request id (read-only):

```bash
.venv/bin/python -m advancore.agent_runner controller-transport driver-show
.venv/bin/python -m advancore.agent_runner controller-transport driver-show CTE-xxxx
```

### Controller decision records

After a controller/reviewer reviews a bundle, they may record a deterministic,
machine-readable decision under `.agent_runner/decisions/`. The decision record
links unambiguously to one existing review bundle and captures only bounded safe
metadata:

- timestamp,
- task ID and filename,
- review-bundle path/reference,
- review-bundle task identity,
- review-bundle branch,
- review-bundle pre/post HEAD when available,
- controller decision (`APPROVE`, `REWORK`, or `BLOCKED`),
- bounded rationale/note,
- actor role,
- decision-record version.

Allowed controller decisions are exactly:

- `APPROVE` — independent controller accepts the implementation for the next
  human-gated publication step.
- `REWORK` — implementation requires further worker changes.
- `BLOCKED` — review cannot proceed safely or required evidence/decision is
  missing.

The `APPROVE` value is a decision-record value only. It does **not** stage,
commit, push, merge, deploy, or automatically transition the task lifecycle.
Recording a decision requires an explicit `record` invocation; inspection via
`show` is read-only.

Decision records exclude credentials, environment dumps, connection strings,
full task bodies, full worker transcripts, customer/business data, and arbitrary
command output. Decision-record creation is appended to the local audit trail.

### Controller decision lifecycle bridge

A controller decision record is evidence of a controller decision; it is not
permission to bypass lifecycle state. The `decision_lifecycle_bridge` module
connects a validated decision record to the existing authority-aware lifecycle
state machine through a bounded, fail-closed bridge.

The bridge is invoked through the `controller-decision apply` subcommand. By
default it previews the mapped lifecycle transition; an explicit `--apply` flag
is required to request a mutation, and then only the linked task file's
`STATUS:` line is rewritten through the existing `transition_task()` helper.

Before any mutation, the bridge validates:

- the decision record exists and parses correctly,
- the decision value is one of `APPROVE`, `REWORK`, or `BLOCKED`,
- the actor role is `controller` or `owner`, never `worker`,
- the linked review bundle exists and parses correctly,
- decision, bundle, and task task IDs agree,
- decision, bundle, and task filenames agree,
- the current branch matches the branch captured in the review bundle,
- the linked task file exists and its identity matches,
- the requested lifecycle transition is valid for the task's current status and
decision actor.

The bridge surfaces HEAD/branch freshness evidence (current HEAD, bundle pre
HEAD, bundle post HEAD) without silently inventing or enforcing a new owner
policy about HEAD equality. Missing, malformed, inconsistent, stale, or
ambiguous linkage evidence fails closed.

Controller decisions map to requested lifecycle targets as follows:

- `APPROVE` → `APPROVED`
- `REWORK` → `REWORK`
- `BLOCKED` → `BLOCKED`

The bridge reuses `is_transition_allowed()` and `transition_task()` from the
TASK-009 lifecycle module; it does not create a parallel authority model. For
example, an `APPROVE` decision against a task in `REVIEW` may preview or apply
`REVIEW → APPROVED`, but the same decision against a task in `READY`,
`IN_PROGRESS`, or `REWORK` is denied because the existing state machine does not
permit a direct transition to `APPROVED` from those states.

Every bridge preview/apply attempt appends a safe metadata record to
`.agent_runner/audit/runner.jsonl`. The record contains the task identity,
decision, target status, transition allowed/applied flags, branch, HEAD, and
paths to the decision record and review bundle. It excludes task bodies, worker
transcripts, credentials, environment dumps, arbitrary notes, and business or
customer data.

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

### Governed proposal-planner fallback (TASK-028)

Goal-task planning uses the fixed code-owned registry `dry-run`, `kimi`,
`kimi-swarm`, and `codex`. Codex planning is a local, ephemeral, read-only
single-prompt invocation with interactive approval denied. Kimi proposal calls
use the same timeout and process-group cleanup boundary as implementation
workers, but receive only the proposal instruction and no implementation or
task-file authority.

Fallback is disabled by default. An operator may configure one explicit hop,
for example `--planner kimi-swarm --fallback-planner codex`. The hop is allowed
only for deterministic executable, quota/capacity, or authentication
availability failures after an independent comparison proves branch, HEAD,
index/worktree, and remotes unchanged. Timeout, cancellation, malformed output,
validation failure, ambiguous failure, or repository mutation stops. The
runner, never a planner, validates the proposal and constructs `STATUS: DRAFT`.

Goal-task artifacts and orchestration checkpoints retain the primary,
configured fallback, terminal planner, timeout, failure classification,
integrity result, and bounded recovery evidence. They exclude prompts,
transcripts, credentials, and arbitrary command output. Resume uses the
checkpointed planner policy and rejects explicit conflicting overrides.

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

Record a controller decision against the latest review bundle:

```bash
.venv/bin/python -m advancore.agent_runner controller-decision record \
  --decision APPROVE \
  --actor controller \
  --note "Accepted for next human-gated publication step"
```

Record a decision against a specific review bundle:

```bash
.venv/bin/python -m advancore.agent_runner controller-decision record \
  .agent_runner/review/20260820T120000_TASK-010.json \
  --decision REWORK \
  --actor controller \
  --note "Add more tests for edge cases"
```

Inspect the latest controller decision record:

```bash
.venv/bin/python -m advancore.agent_runner controller-decision show
```

Inspect a specific decision record:

```bash
.venv/bin/python -m advancore.agent_runner controller-decision show .agent_runner/decisions/20260821T120000_TASK-011_APPROVE.json
```

Preview the lifecycle effect of the latest controller decision:

```bash
.venv/bin/python -m advancore.agent_runner controller-decision apply
```

Preview the effect of a specific decision record:

```bash
.venv/bin/python -m advancore.agent_runner controller-decision apply .agent_runner/decisions/20260821T120000_TASK-012_APPROVE.json
```

Explicitly apply the decision to the linked task lifecycle:

```bash
.venv/bin/python -m advancore.agent_runner controller-decision apply --apply
```

Prepare a controller handoff request from the latest review bundle:

```bash
.venv/bin/python -m advancore.agent_runner controller-handoff prepare
```

Prepare a handoff request from a specific review bundle:

```bash
.venv/bin/python -m advancore.agent_runner controller-handoff prepare .agent_runner/review/20260820T120000_TASK-010.json
```

Reconcile the latest handoff request with the latest controller decision:

```bash
.venv/bin/python -m advancore.agent_runner controller-handoff reconcile
```

Reconcile specific artifacts:

```bash
.venv/bin/python -m advancore.agent_runner controller-handoff reconcile \
  .agent_runner/controller_handoff/20260821T120000_TASK-013_WAITING_DECISION.json \
  .agent_runner/decisions/20260821T130000_TASK-013_APPROVE.json
```

Inspect the latest handoff request:

```bash
.venv/bin/python -m advancore.agent_runner controller-handoff show
```

Inspect a specific handoff request:

```bash
.venv/bin/python -m advancore.agent_runner controller-handoff show .agent_runner/controller_handoff/20260821T120000_TASK-013_WAITING_DECISION.json
```

Dispatch the built-in manual controller adapter for the latest handoff request:

```bash
.venv/bin/python -m advancore.agent_runner controller-adapter dispatch
.venv/bin/python -m advancore.agent_runner controller-adapter dispatch latest --adapter manual
```

Dispatch the adapter for a specific handoff request:

```bash
.venv/bin/python -m advancore.agent_runner controller-adapter dispatch .agent_runner/controller_handoff/20260821T120000_TASK-014_WAITING_DECISION.json --adapter manual
```

Read-only inspection of a handoff request through the controller adapter:

```bash
.venv/bin/python -m advancore.agent_runner controller-adapter status
.venv/bin/python -m advancore.agent_runner controller-adapter status .agent_runner/controller_handoff/20260821T120000_TASK-014_WAITING_DECISION.json
```

Create a transport request envelope from the latest handoff request:

```bash
.venv/bin/python -m advancore.agent_runner controller-transport request
.venv/bin/python -m advancore.agent_runner controller-transport request .agent_runner/controller_handoff/20260821T120000_TASK-015_WAITING_DECISION.json --adapter manual
```

Inspect the latest transport envelope (read-only):

```bash
.venv/bin/python -m advancore.agent_runner controller-transport show
.venv/bin/python -m advancore.agent_runner controller-transport show .agent_runner/controller_transport/20260821T120000_TASK-015_CTE-xxxx_request.json
```

Validate the latest transport response envelope and reconcile any returned decision:

```bash
.venv/bin/python -m advancore.agent_runner controller-transport validate-response
.venv/bin/python -m advancore.agent_runner controller-transport validate-response .agent_runner/controller_transport/20260821T130000_TASK-015_CTE-xxxx_response.json
```

Send a transport request envelope through the local driver:

```bash
.venv/bin/python -m advancore.agent_runner controller-transport driver-send
.venv/bin/python -m advancore.agent_runner controller-transport driver-send .agent_runner/controller_handoff/20260821T120000_TASK-016_WAITING_DECISION.json
```

Receive a transport response envelope through the local driver:

```bash
.venv/bin/python -m advancore.agent_runner controller-transport driver-receive
.venv/bin/python -m advancore.agent_runner controller-transport driver-receive CTE-xxxx
```

Show local driver artifacts for a request id (read-only):

```bash
.venv/bin/python -m advancore.agent_runner controller-transport driver-show
.venv/bin/python -m advancore.agent_runner controller-transport driver-show CTE-xxxx
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
- The decision-lifecycle bridge is tested for decision mapping, preview/apply
  behaviour, authority restrictions, identity/branch linkage validation,
  lifecycle-state obedience, HEAD evidence surfacing, audit metadata, and
  absence of Git-publication side effects.
- The controller-adapter boundary is tested for interface behavior, the built-in
  `manual` adapter, fake/stub adapters, result-state validation, worker/controller
  authority separation, handoff linkage, reconciliation delegation, read-only
  inspection, failure handling, audit behavior, and absence of Git/lifecycle side
  effects.
- The controller-transport envelope is tested for request/response construction,
  deterministic serialization round-trip, schema/version/state validation,
  correlation/reference mismatch rejection, safe-field policy, path traversal
  rejection, response conversion, response reconciliation delegation through
  TASK-013, authority separation (PENDING/BLOCKED create no authority;
  DECISION_RECEIVED requires a valid decision record), read-only inspection,
  audit behavior, and absence of Git/lifecycle/task mutation.
- The controller transport-driver boundary is tested for interface behavior,
  local-filesystem send/receive round-trip, idempotency, conflict detection,
  correlation/reference binding, path safety, symlink escape rejection where
  supported, read-only inspection, authority separation (driver never treats
  transport success as approval and never mutates lifecycle/Git/database state),
  and delegation of decision reconciliation to existing TASK-015/TASK-013 helpers.
- CLI tests patch `get_git_info` directly and verify exit codes.
- TASK-026 owner-action acceptance tests exercise the production resume,
  lifecycle, decision, handoff, checkpoint, report, and finalization-delegation
  path across both approval gates with controlled local fakes. They also prove
  preview non-mutation, exact evidence correlation, fail-closed replay/override
  guards, worker authority separation, and terminal idempotency.

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
| Worker self-approval through decision record | Decision records reject `worker` actors; `APPROVE` does not mutate Git, remote, or task lifecycle state. |
| Missing or inconsistent review bundle evidence | Decision-record builder validates bundle linkage and fails closed on missing/inconsistent task identity, branch, or HEAD. |
| Decision record leaks secrets or full content | Decision records exclude credentials, env dumps, full task bodies, worker transcripts, and arbitrary output. |
| Decision applied to wrong task or branch | Bridge re-validates decision/bundle/task identity and current branch; mismatches fail closed. |
| `APPROVE` decision bypassing lifecycle state | Bridge maps `APPROVE` to `APPROVED` and reuses `transition_task()`; invalid current states are denied. |
| Worker self-approval through bridge | Bridge rejects `worker` actors; only `controller`/`owner` may apply a decision. |
| Hidden task mutation by bridge | Bridge default is preview; explicit `--apply` is required and only the `STATUS:` line is rewritten. |
| Bridge audit leaks secrets or full content | Bridge audit records exclude task bodies, transcripts, credentials, env dumps, notes, and business/customer data. |
| Missing explicit handoff object between bundle and decision | Handoff request stores bounded metadata and a stable reference to the review bundle. |
| Handoff request treated as approval | Handoff state is `WAITING_DECISION` until a separate controller decision record is reconciled. |
| Worker self-approval through handoff queue | Reconciliation rejects `worker` actors and validates decision/task/bundle linkage. |
| Silent replacement of a reconciled decision | Reconciliation is idempotent for the same decision and fails closed for a different decision. |
| Handoff artifacts leak secrets or full content | Handoff requests exclude task bodies, transcripts, credentials, env dumps, and business/customer data. |
| Worker self-approval through controller adapter | Adapter dispatch delegates decision validation/reconciliation to TASK-013, which rejects `worker` actors and task/bundle mismatches. |
| Adapter treated as approval authority | Adapters return only `PENDING`, `DECISION_RECEIVED`, or `BLOCKED`; the built-in `manual` adapter never synthesizes an `APPROVE` decision. |
| Remote/network transport introduced unintentionally | The built-in adapter is `manual`; no HTTP client/server, webhook, or subprocess execution is implemented. |
| Adapter dispatch mutates lifecycle/Git/database state | Dispatch only reads the handoff and reconciles a returned decision through TASK-013; it never calls the TASK-012 bridge or Git publication commands. |
| Transport envelope treated as controller authority | The envelope is data exchange only; `DECISION_RECEIVED` still requires a separately valid TASK-011 decision record reconciled through TASK-013. |
| Transport envelope carries full task body or secrets | Envelope fields are bounded to references and metadata already authorized by TASK-010/TASK-013/TASK-014; full bodies, transcripts, credentials, and customer data are excluded. |
| Unknown/mismatched envelope version, schema, state, or references | Envelope validation fails closed on unknown versions/schemas, unknown states, missing fields, and correlation/reference mismatches. |
| Path traversal via envelope artifact paths | Envelope path resolution rejects paths that escape the repository root; generated filenames are sanitized. |
| Transport response applied without reconciling decision | `apply_transport_response()` delegates decision validation/reconciliation to existing TASK-013 logic; worker-authored or mismatched decisions remain rejected. |
| Transport envelope operations mutate Git/lifecycle/database state | Envelope operations write only local `.agent_runner/controller_transport/` artifacts and audit metadata; they do not mutate task files, Git state, lifecycle state, or database state. |
| Transport driver assumes controller authority | The driver is delivery plumbing only; it does not create, infer, approve, reconcile, apply, publish, or deploy. |
| Driver send/receive mutates lifecycle/Git/database state | Driver operations write only local `.agent_runner/controller_transport/outbox/` and `inbox/` artifacts; they do not invoke the TASK-012 lifecycle bridge or mutate task files, Git state, or database state. |
| Driver treats `DECISION_RECEIVED` as approval | A `DECISION_RECEIVED` response returned by the driver still requires existing TASK-011/TASK-013/TASK-014/TASK-015 validation/reconciliation before any lifecycle action. |
| Driver silently overwrites conflicting artifacts | Identical request resend is idempotent; divergent requests or ambiguous responses for the same correlation id fail closed. |
| Path traversal/symlink escape via driver artifacts | Driver read/write paths are resolved and checked against the bounded `outbox/` and `inbox/` directories; escapes are rejected. |
| Unintended remote transport via driver | Only the local-filesystem driver is implemented; no HTTP, webhooks, sockets, queues, background polling, or subprocess transport is added. |
| Autonomous repair bypassing governance | Repair is opt-in (`--repair-attempts`), capped at 2, and fails closed on non-repairable governance violations. |
| Repair prompt leaking secrets or full transcripts | Repair evidence is bounded to metadata and short summaries; full stdout/stderr, env dumps, and arbitrary repo content are excluded. |
| Repair loop mutating branch/HEAD or staging | Full verification reruns after each attempt; branch/HEAD/staging failures are classified `NON_REPAIRABLE` and stop immediately. |
| Repair loop granting controller authority | Successful repair ends only at `READY_FOR_APPROVAL`; no commit, push, merge, deploy, or lifecycle approval occurs. |

---

## 12. Governed auto-pipeline

TASK-017 adds a single-command governed development pipeline that automates the
repetitive gates between task discovery and controller review while preserving
the authority boundaries established by TASK-005 through TASK-016.

### 12.1 Command

```bash
.venv/bin/python -m advancore.agent_runner auto TASK-018 --worker kimi-swarm
```

The default worker is `dry-run`. Use `--worker kimi` for the standard Kimi
prompt adapter or `--worker kimi-swarm` for the swarm-mode adapter.

Use `--repair-attempts N` (0-2, default 0) to enable a bounded autonomous repair
loop. A value of `0` preserves the original TASK-017 single-pass behavior; any
non-zero value triggers recoverable-failure classification and re-prompts the
selected worker with bounded evidence. Values above `2` are clamped to `2`.

### 12.2 Gates (executed in order, fail-closed)

1. Resolve and parse the approved task file.
2. Parse and validate the task's `Allowed changed-file scope` section.
3. Validate branch is not `main`, working tree is clean, and task status is
   executable (`READY`/`REWORK`).
4. Launch the selected worker adapter.
5. Capture pre/post Git snapshots (reuse TASK-005/TASK-007 verification).
6. Generate the review bundle and audit record (reuse TASK-006/TASK-010).
7. Detect any staged/index changes created by the worker.
8. Run the full repository pytest suite.
9. Run `git diff --check` for unstaged and staged changes.
10. Compare actual changed paths against the allowed scope.
11. Write a bounded auto-pipeline artifact and produce a consolidated
    controller-ready report.
12. If `--repair-attempts` is enabled and the failure is classified as
    repairable, build a bounded repair prompt and re-run steps 4-11. Repeat
    until the run passes or the repair budget is exhausted. Non-repairable
    governance failures (branch/HEAD mutation, staged changes, scope violations,
    etc.) fail closed immediately and are reported as `NON_REPAIRABLE`.

The pipeline stops at the first failing gate (or after exhausting the repair
budget) and never stages, commits, pushes, merges, switches branches, deploys,
or mutates lifecycle state.

### 12.3 Allowed changed-file scope

Auto mode requires an explicit `## Allowed changed-file scope` section in the
task file. The section lists backtick-quoted repository-relative paths that the
worker is permitted to modify. The pipeline fails closed if:

- the section is missing,
- an allowed path is absolute, contains `..`, or otherwise escapes the repo,
- any actual changed path (tracked modification, untracked file, deletion, or
  rename target) is outside the allowed set.

### 12.4 Worker adapters

- `DryRunWorkerAdapter` — default; performs no real work.
- `KimiWorkerAdapter` — bounded `kimi --prompt` invocation.
- `KimiSwarmWorkerAdapter` — uses the same safe `kimi --prompt` boundary
  because the installed Kimi CLI does not expose a documented non-interactive
  swarm subcommand. It sends a canonical instruction that explicitly requests
  Kimi's AgentSwarm capability and restates the task scope and prohibited
  actions. It never adds `--auto`, `--yolo`, or other permission-bypass flags.

### 12.5 Pipeline result states

- `READY_FOR_APPROVAL` — all gates passed; the work awaits controller/owner
  review.
- `VALIDATION_FAILED` — branch, working-tree, or task-status gate failed.
- `WORKER_FAILED` — the worker returned a non-zero result.
- `POST_WORKER_VERIFICATION_FAILED` — branch/HEAD moved unexpectedly.
- `TEST_FAILED` — pytest failed.
- `DIFF_CHECK_FAILED` — `git diff --check` detected whitespace errors.
- `SCOPE_FAILED` — scope missing/unsafe or actual changes exceed allowed paths.
- `ARTIFACT_FAILED` — the auto-pipeline artifact could not be written.
- `REPAIR_EXHAUSTED` — the repair budget was consumed without producing a
  passing run; controller/owner review is required.
- `NON_REPAIRABLE` — a governance or safety failure cannot be autonomously
  repaired; controller/owner review is required immediately.

### 12.6 Auto artifact

Each run appends a bounded JSON Lines record to
`.agent_runner/auto/auto_pipeline.jsonl` (gitignored). The record contains only
safe metadata: task identity, branch, HEAD SHAs, worker type, pytest/diff-check
results, allowed/actual paths, scope result, and a statement that no publication
occurred. It excludes full task bodies, worker transcripts, secrets, environment
dumps, and customer data.

### 12.7 Authority boundary

A successful auto run means only:

```
IMPLEMENTATION + VERIFICATION COMPLETE → READY FOR CONTROLLER/OWNER REVIEW
```

It does **not** mean approved, committed, pushed, merged, or deployed. The
AdvanCore runner remains the policy authority; Kimi/Kimi Swarm remains a bounded
implementation worker.

### 12.8 Autonomous repair loop (TASK-018)

When `--repair-attempts N` is enabled, the runner classifies the initial
failure as either repairable or non-repairable:

- **Repairable:** `TEST_FAILED`, `DIFF_CHECK_FAILED`, and `WORKER_FAILED` (when
  branch/HEAD/staging checks are still clean). The runner sends the selected
  worker a bounded repair instruction that contains only the triggering gate,
  attempt number, bounded evidence, and the task's allowed changed-file scope.
- **Non-repairable:** `VALIDATION_FAILED`, `POST_WORKER_VERIFICATION_FAILED`,
  `SCOPE_FAILED`, `ARTIFACT_FAILED`, and any other governance or ambiguous
  state. These stop immediately and are reported as `NON_REPAIRABLE`.

The repair instruction:

- restates the task ID, task file, and allowed changed-file scope,
- includes only bounded metadata (return codes, short summaries) and never full
  worker transcripts, secrets, environment dumps, or arbitrary repository
  content,
- explicitly forbids `--auto`, `--yolo`, permission-bypass modes, destructive
  Git operations, staging, commit, push, merge, branch switch, credential
  access, deployment, and self-approval,
- is sent through the same worker adapter selected for the original attempt
  (preserving `kimi-swarm` when already chosen).

After every repair attempt the full verification sequence reruns: post-worker
Git/branch/HEAD checks, staged-path detection, full pytest, `git diff --check`,
and exact changed-file scope verification. A successful repair ends only at
`READY_FOR_APPROVAL`; it never stages, commits, pushes, merges, deploys, or
mutates lifecycle state.

The auto artifact records bounded per-attempt metadata (attempt number,
triggering gate, status, worker type, worker success, verification status, and
evidence keys) without storing full transcripts or command output.

---

## 13. Future extension points

- Additional `WorkerAdapter` implementations for other local or remote workers.
- Integration with GitHub Issues/PRs for task discovery (read-only first).
- Background/scheduled execution only after explicit policy tasks define it.
- Approval-gate state persistence once an auditable store is approved.
- Optional bundle signing or checksums if tamper-evident handoff is required.
- Controller adapter or remote transport layered on top of the existing handoff
  request/decision linkage contract without redesigning governance.
- Remote controller transport implementations that consume the versioned
  `controller_transport` request/response envelope and serialize it over an
  approved network mechanism (e.g. HTTP, webhook, queue) in a future task.
- Additional transport-driver implementations that satisfy the
  `ControllerTransportDriver` contract for other delivery mechanisms, while
  preserving the same envelope and authority boundaries.

---

## 14. Reasoning labels

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
- Controller decision records are stored under `.agent_runner/decisions/` and contain only bounded safe metadata.
- Allowed controller decisions are exactly `APPROVE`, `REWORK`, and `BLOCKED`.
- The actor role `worker` cannot create a controller decision record.
- An `APPROVE` decision record does not stage, commit, push, merge, deploy, or automatically transition a task.
- The `controller-decision apply` subcommand previews the mapped lifecycle transition by default.
- An explicit `--apply` flag is required for the bridge to mutate the linked task file.
- The bridge maps `APPROVE` → `APPROVED`, `REWORK` → `REWORK`, and `BLOCKED` → `BLOCKED`.
- The bridge reuses `is_transition_allowed()` and `transition_task()` from the TASK-009 lifecycle module.
- The bridge validates decision record existence/parseability, actor role, decision value, review-bundle linkage, task identity, current branch, and lifecycle transition validity before applying any mutation.
- The bridge surfaces HEAD/branch freshness evidence but does not enforce a current-HEAD-equals-bundle-HEAD policy.
- Bridge preview/apply attempts append a safe metadata audit record with mode `bridge` to `.agent_runner/audit/runner.jsonl`.
- Controller handoff requests are stored under `.agent_runner/controller_handoff/` and contain only bounded safe metadata.
- Allowed handoff states are `WAITING_DECISION`, `DECISION_RECEIVED`, and `BLOCKED`.
- A handoff request is created only from a valid review bundle with supported recommended action and matching branch evidence.
- Reconciliation validates request/decision parseability, actor role, task identity, bundle reference, and branch/HEAD evidence consistency.
- Reconciliation is idempotent when the same decision is reconciled again and fails closed when a different decision is already reconciled.
- Handoff prepare/reconcile write only local `.agent_runner/` artifacts and do not mutate task files, Git state, or lifecycle state.
- Handoff prepare/reconcile attempts append safe metadata audit records with modes `handoff_prepare` and `handoff_reconcile` to `.agent_runner/audit/runner.jsonl`.
- The controller-adapter boundary lives in `advancore/agent_runner/controller_adapter.py`.
- Allowed controller-adapter result states are `PENDING`, `DECISION_RECEIVED`, and `BLOCKED`.
- The built-in controller adapter is `manual`; it is local, performs no network or subprocess execution, and does not synthesize controller decisions.
- Controller adapters receive only bounded handoff metadata and safe references; they do not receive full task bodies, worker transcripts, credentials, environment dumps, or arbitrary repository contents.
- Adapter dispatch loads exactly one selected adapter, validates the returned result state, and reconciles any reported decision through the existing TASK-013 handoff reconciliation logic.
- Adapter dispatch does not invoke the TASK-012 lifecycle bridge and does not mutate task lifecycle state.
- Adapter dispatch/status does not stage, commit, push, merge, deploy, switch branches, or access secrets.
- Adapter dispatch attempts append a safe metadata audit record with mode `controller_adapter` to `.agent_runner/audit/runner.jsonl`.
- `controller-adapter status` is read-only and does not reconcile decisions or write artifacts.
- The governed auto-pipeline lives in `advancore/agent_runner/auto_pipeline.py` and is invoked through the `auto` subcommand.
- Auto mode requires an explicit `Allowed changed-file scope` section in the task file and enforces it fail-closed.
- The auto-pipeline runs validation, worker execution, review-bundle generation, full pytest, `git diff --check`, and exact scope verification in order and stops immediately on any failed gate.
- The auto-pipeline reuses existing `execute()`, audit, and review-bundle semantics from TASK-005 through TASK-010.
- The auto-pipeline writes a bounded JSON Lines artifact under `.agent_runner/auto/auto_pipeline.jsonl` and excludes full task bodies, worker transcripts, secrets, environment dumps, and customer/business data.
- Auto-pipeline success means only `READY_FOR_APPROVAL`; it never means `APPROVED`, `COMMITTED`, `PUSHED`, `MERGED`, or `DEPLOYED`.
- The `KimiSwarmWorkerAdapter` uses the documented `kimi --prompt` boundary because the installed Kimi CLI does not expose a documented non-interactive swarm subcommand.
- The swarm adapter instruction explicitly requests AgentSwarm capability, restates the allowed changed-file scope, and forbids staging, commit, push, merge, branch switch, credential access, deployment, and self-approval.
- The swarm adapter never adds `--auto`, `--yolo`, or equivalent permission-bypass flags.
- The `auto` subcommand supports `--repair-attempts N` (default `0`, clamped to `0-2`) to enable a bounded autonomous repair loop.
- Autonomous repair classifies failures as `REPAIRABLE` (`TEST_FAILED`, `DIFF_CHECK_FAILED`, safe `WORKER_FAILED`) or `NON_REPAIRABLE` (governance/branch/HEAD/staging/scope/artifact failures).
- Repair instructions contain only bounded failure evidence (triggering gate, attempt number, return codes, short summaries) and never full worker transcripts, secrets, environment dumps, or arbitrary command output.
- Repair instructions restate the task's allowed changed-file scope and prohibited actions for every attempt.
- The full verification sequence (post-worker Git/branch/HEAD checks, staged-path detection, pytest, `git diff --check`, exact scope verification) reruns after every repair attempt.
- A successful repair ends only at `READY_FOR_APPROVAL`; it never stages, commits, pushes, merges, deploys, or mutates lifecycle state.
- Repair budget exhaustion is reported as `REPAIR_EXHAUSTED`; non-repairable failures are reported as `NON_REPAIRABLE`.
- The auto artifact records bounded per-attempt metadata (attempt number, triggering gate, status, worker type, worker success, verification status, evidence keys) without full transcripts or command output.
- The controller-transport envelope lives in `advancore/agent_runner/controller_transport.py`.
- Transport request and response envelopes are versioned (`envelope_version: "1"`) and schema-tagged (`advancore.controller.transport.request` / `.response`).
- Transport envelopes carry only bounded safe metadata: correlation/request ID, task identity, handoff and review-bundle references, adapter name/type, bundle branch/HEAD/recommended-action/handoff-state, and bounded messages.
- Transport envelopes exclude full task bodies, worker transcripts, credentials, environment dumps, secrets, customer/business data, and arbitrary repository contents.
- Allowed transport response result states are `PENDING`, `DECISION_RECEIVED`, and `BLOCKED`.
- Envelope validation fails closed on unknown versions, unknown schemas, unknown states, malformed JSON, missing required fields, and mismatched correlation/task/handoff/bundle references.
- Path traversal/escape is rejected when resolving envelope artifact paths against the repository root.
- A transport response envelope is never itself an approval or lifecycle authorization.
- `apply_transport_response()` delegates controller-decision validation and reconciliation to the existing TASK-013 `reconcile_controller_handoff()` logic.
- Transport envelope operations write only local `.agent_runner/controller_transport/` artifacts and `mode: "controller_transport"` audit records; they do not mutate task files, Git state, lifecycle state, or database state.
- `controller-transport show` is read-only and does not write artifacts, reconcile decisions, or mutate repository state.
- The controller transport-driver boundary lives in `advancore/agent_runner/controller_transport_driver.py`.
- The transport-driver contract is defined by the abstract `ControllerTransportDriver` class with `send`, `receive`, and `show` operations.
- The built-in transport driver is `LocalFilesystemTransportDriver`, which stores requests under `.agent_runner/controller_transport/outbox/` and responses under `.agent_runner/controller_transport/inbox/`.
- The driver consumes the existing TASK-015 `ControllerTransportRequest` and `ControllerTransportResponse` envelope types rather than inventing a second envelope model.
- Driver `send` validates the request through the existing TASK-015 helper and writes only under the bounded local transport directory.
- Driver `receive` validates the response through the existing TASK-015 helper and binds it to the expected task, correlation/request id, handoff path, and review-bundle path.
- Identical request resend is idempotent; conflicting duplicates for the same correlation id fail closed.
- Missing, ambiguous, malformed, or reference-mismatched responses fail closed.
- Driver read/write paths are resolved and checked against the bounded `outbox/` and `inbox/` directories; path traversal and symlink escape are rejected.
- Driver `show` is read-only and does not mutate artifacts, reconcile decisions, or invoke the lifecycle bridge.
- Driver send/receive does not invoke the TASK-012 lifecycle bridge and does not mutate task files, Git state, or database state.
- A `DECISION_RECEIVED` response from the driver still requires existing TASK-011/TASK-013/TASK-014/TASK-015 validation/reconciliation before any lifecycle action.
- The local-filesystem driver performs no network, subprocess, credential, or background-polling operations.
- `controller-transport driver-send`, `driver-receive`, and `driver-show` are local-only CLI operations that reuse the existing `controller_transport` audit mode.
- Controller-gated finalization lives in `advancore/agent_runner/finalize.py` and is invoked through the `finalize` CLI subcommand.
- The finalizer defaults to preview/dry-run; `--apply` is required to mutate lifecycle state, index, HEAD, or remote state.
- The finalizer requires a separately valid controller `APPROVE` decision and rejects worker-authored, missing, or non-`APPROVE` decisions.
- Finalization binds task id, task filename, branch, HEAD, review-bundle path, and verified changed-path set to current repository state and fails closed on mismatch.
- Worker lifecycle transitions orchestrated by the finalizer are limited to `READY → IN_PROGRESS → REVIEW` and are attributed/audited as `worker`.
- Controller approval `REVIEW → APPROVED` is applied through the existing decision-lifecycle bridge and is attributed/audited as `controller`.
- The finalizer stages only the explicit verified path set plus the legitimately modified task file; it never uses `git add .`, `-A`, or wildcards.
- The finalizer creates exactly one local non-merge commit and verifies parent, tree, and contents before push.
- Push is limited to normal `git push origin <current-branch>` targeting `origin/<same-branch>`; force push, history rewrite, tag creation, ref deletion, and merge commits are impossible.
- `main` cannot be finalized or pushed through this command.
- Finalization audit records use modes `finalize` and are written to `.agent_runner/audit/runner.jsonl`; successful attempts also write `.agent_runner/finalize/finalize.jsonl`.
- Finalization artifacts contain only bounded safe metadata and exclude full task bodies, worker transcripts, credentials, secrets, environment dumps, and customer/business data.

### ASSUMPTION

- Future tasks will define the next approval gates before commit/push become
  automated.
- Kimi Code's `--prompt` mode remains a suitable bounded invocation.

### INFERENCE

- Keeping the runner local, explicit, and fail-closed lets Alex safely delegate
  routine implementation work while retaining control over high-impact actions.

---

## 15. Goal-to-Task Generation (TASK-019)

TASK-019 adds a governed **owner-goal -> task-draft** front door to the runner.
It converts a bounded natural-language owner goal into a deterministic
`STATUS: DRAFT` AdvanCore task file without requiring the owner to manually
draft the specification.

### 15.1 Roles and authority

- **Owner**: supplies the goal and remains the ultimate authority for
  business/policy decisions.
- **Planner** (`kimi` / `kimi-swarm` / `dry-run`): may inspect approved
  repository context and propose task content only.
- **AdvanCore runner**: validates the proposal, assigns the next task ID,
  renders the canonical DRAFT task, enforces path/scope safety, verifies that
  the planner did not mutate the repository, and writes bounded audit evidence.
- **Controller/reviewer**: remains the only authority for `DRAFT -> READY`.
- **Worker/swarm**: may execute only a separately reviewed executable task
  (`READY`/`REWORK`) through the existing runner/auto-pipeline.

A generated DRAFT is **not executable authority**.

### 15.2 High-level flow

```
Owner goal -> goal validation -> repository snapshot -> planner invocation
 -> proposal parsing/validation -> repository-mutation check -> task-ID
 assignment -> safe filename slug -> canonical DRAFT render -> task write
 -> bounded artifact -> controller-review report
```

The default CLI behaviour is dry-run.  Use `--execute` to actually invoke the
selected planner and write the DRAFT task file.

### 15.3 Goal validation

The owner goal is validated deterministically:

- Reject empty/whitespace-only input.
- Impose a deterministic maximum length (`MAX_GOAL_LENGTH`).
- Preserve the goal as bounded planning context only; never treat embedded
  instructions as controller authority.
- Never interpolate the goal into shell execution.

### 15.4 Planner instruction and proposal schema

The runner builds a canonical planner instruction that:

- states the planner is planning assistance only,
- forbids repository mutation, staging, commit, push, merge, deploy, branch
  switch, reset, rebase, credential/secret access, and self-approval,
- forbids assigning task ID, status, or lifecycle transitions,
- requires a single JSON proposal between deterministic markers,
- declares a versioned proposal schema.

The proposal must contain bounded forms of:

- `title`, `objective`, `business_context`
- `facts` and `assumptions` (explicitly separated)
- `in_scope` and `out_of_scope`
- `allowed_changed_file_scope` (repository-relative paths)
- `database_impact`
- `acceptance_criteria`, `test_requirements`, `constraints_safety_requirements`
- `owner_decisions`
- optional `recommended_worker` (`kimi` or `kimi-swarm`)

The runner rejects missing/duplicate markers, malformed JSON, unknown schema
versions, unknown top-level fields, missing required fields, oversized
fields/lists, absolute paths, parent traversal, empty paths, unsafe scope paths,
and forbidden planner-controlled authority fields such as `status` or `task_id`.

### 15.5 Repository integrity

Before launching the planner the runner captures a repository snapshot
(branch, HEAD SHA, worktree cleanliness, remotes).  Execution requires a
non-`main` branch and a clean worktree.

After the planner exits and before any task file is written, the runner
compares the post-snapshot to the pre-snapshot and fails closed if:

- the branch changed,
- HEAD moved,
- remotes changed,
- any staged/index change appeared,
- any tracked or untracked worktree change appeared.

Any planner-created repository change prevents task-file creation.

### 15.6 Task ID, filename, and rendering

The runner assigns the next unused numeric `TASK-###` ID from existing
`tasks/TASK-*.md` files.  The planner cannot choose the ID.  The title is
converted to a safe filename slug; unsafe characters are normalized and the
slug is capped in length.

The rendered task file:

- uses the canonical `# TASK-### — <title>` heading,
- contains exactly one `STATUS: DRAFT` line,
- includes Objective, Business context, Facts, Assumptions, In scope,
  Explicitly out of scope, Allowed changed-file scope, Database impact,
  Safety requirements, Acceptance criteria, Test requirements, Constraints,
  Owner decisions, and a Completion report skeleton,
- injects fixed runner-owned governance language,
- preserves unresolved owner decisions explicitly.

### 15.7 Artifact and audit

Each generation attempt appends a bounded JSON Lines record to
`.agent_runner/goal_task/goal_task.jsonl` (gitignored).  The record contains
only safe metadata: goal hash, short goal summary, planner type, schema
version, assigned task ID/path, pre/post branch/HEAD, validation result, owner
decision count, whether a task file was written, and a `no_publication_performed`
flag.  It excludes full planner transcripts, environment dumps, credentials,
secrets, and arbitrary repository content.

### 15.8 CLI

The `goal-task` subcommand accepts:

- `--goal "..."` (required bounded owner goal),
- `--planner {dry-run,kimi,kimi-swarm}` (default `dry-run`),
- `--execute` to launch the planner and write the DRAFT task.

Dry-run mode validates the goal, determines the next candidate task ID, and
reports intended behaviour without launching Kimi or writing a task file.

Execute mode runs all validations, invokes the selected planner, validates its
proposal, verifies repository integrity, and writes only the new DRAFT task
file.

### 15.9 Governance guarantees

- The planner proposes; the runner constructs; the controller/owner
  authorizes execution.
- The generated task is always `STATUS: DRAFT`.
- No automatic `DRAFT -> READY` transition occurs.
- No staging, commit, push, merge, deploy, branch switch, reset, rebase, or
  history rewrite is performed.
- No task implementation worker is automatically launched on the generated
  task.
- `main` remains untouched.
- Unknown, malformed, unsafe, conflicting, or ambiguous states fail closed.


---

## 16. Controller-Gated Finalization and Branch Publication (TASK-020)

### 16.1 Purpose

TASK-020 adds a single bounded publication path that consumes a separately valid
controller `APPROVE` decision for a successfully verified auto-pipeline result,
applies only the already-authorized lifecycle transitions, stages exactly the
verified task scope, creates one local commit, and pushes only the current
non-`main` feature branch.

The finalizer replaces the repetitive manual sequence:

```
worker lifecycle transitions → controller approval transition → git add exact files
→ staged verification → commit → clean-tree verification → commit-content verification
→ push → post-push status
```

with one governed command while preserving every existing authority boundary.

### 16.2 Governance principle

**Verification is evidence. Controller approval is authority. Finalization
executes authority; it does not create it.**

The finalizer never:

- infers `APPROVE` from passing tests or `READY_FOR_APPROVAL`;
- accepts worker/swarm/Kimi approval;
- skips lifecycle states;
- stages files outside the verified path set;
- commits when staged scope differs from verified scope;
- pushes `main` or any branch other than the current verified feature branch;
- force-pushes, rewrites history, creates tags, deletes refs, or merges;
- accesses secrets or credentials beyond already-configured local Git authentication;
- modifies Git remotes or credential configuration;
- continues after stale, mismatched, ambiguous, or unauthorized evidence.

### 16.3 Module and entry point

The implementation lives in `advancore/agent_runner/finalize.py` and is invoked
through the CLI subcommand:

```bash
python -m advancore.agent_runner finalize TASK-020 --decision <path-or-latest>
```

Preview/dry-run is the default. Use `--apply` to execute lifecycle transitions,
staging, commit, and push. An optional `--message` supplies a bounded commit
message; otherwise the message is derived from the task title.

### 16.4 High-level flow

```
Valid controller APPROVE decision + linked review bundle
          │
          ▼
┌─────────────────────┐
│ Identity/freshness  │── task id, filename, branch, HEAD, changed paths
│      gates          │
└─────────────────────┘
          │
          ▼
┌─────────────────────┐
│ Worker transitions  │── READY → IN_PROGRESS → REVIEW (when warranted)
│  (existing authority) │
└─────────────────────┘
          │
          ▼
┌─────────────────────┐
│ Controller approval │── REVIEW → APPROVED via decision-lifecycle bridge
│  (existing authority) │
└─────────────────────┘
          │
          ▼
┌─────────────────────┐
│ Exact-path staging  │── git add <verified paths> only
│  + staged reverify  │
└─────────────────────┘
          │
          ▼
┌─────────────────────┐
│ Bounded commit      │── one non-merge commit, parent/contents verified
└─────────────────────┘
          │
          ▼
┌─────────────────────┐
│ Push current branch │── git push origin <current-branch> only
│  + synchronization  │    to origin/<same-branch>, no force
└─────────────────────┘
```

### 16.5 Gate sequence

1. **Repository snapshot.** Capture current branch and HEAD.
2. **Main rejection.** Finalization is impossible on `main`.
3. **Decision resolution.** Load the controller decision record (explicit path or
   latest under `.agent_runner/decisions/`).
4. **Actor/value validation.** Reject worker-authored, unknown, or non-`APPROVE`
   decisions.
5. **Bundle linkage.** Load and validate the linked review bundle's task identity,
   branch, and HEAD evidence.
6. **Task identity.** Reconcile decision, bundle, and on-disk task file.
7. **Freshness.** Current branch and HEAD must match the bundle evidence.
8. **Clean index.** No staged paths may exist at start.
9. **Scope match.** Current working-tree changed paths must exactly equal the
   bundle's verified `changed_paths`.
10. **Worker lifecycle choreography.** Apply `READY → IN_PROGRESS → REVIEW` only
    when the task status warrants each transition and only under worker actor
    authority.
11. **Controller approval.** Apply `REVIEW → APPROVED` through the existing
    decision-lifecycle bridge under controller actor authority.
12. **Post-transition scope check.** Verify the working tree still contains
    exactly the approved paths (including the legitimately modified task file).
13. **Exact-path staging.** Run `git add` with the explicit verified path list
    only; never `git add .`, `-A`, or wildcards.
14. **Staged reverify.** Confirm staged paths exactly match the approved set.
15. **Whitespace check.** Run `git diff --cached --check` and fail closed on error.
16. **Bounded commit message.** Use `agent: <normalized task title>` or an
    optional controller-supplied message that contains no newlines or carriage
    returns.
17. **Commit.** Create exactly one local commit.
18. **Post-commit verification.** Confirm working tree is clean, commit parent is
    the expected pre-commit HEAD, commit is not a merge commit, and commit
    contents exactly match the approved paths.
19. **Push.** Push only the current verified feature branch to
    `origin/<same-branch>` using normal fast-forward semantics.
20. **Post-push verification.** Confirm local HEAD matches `origin/<same-branch>`
    and the working tree remains clean.

### 16.6 Result statuses

- `READY_TO_FINALIZE` — preview mode validated all gates; apply would proceed.
- `FINALIZED_LOCAL` — lifecycle, staging, and commit succeeded; push not reached
  or not required.
- `PUSHED` — full lifecycle, commit, push, and post-push synchronization
  succeeded.
- `BLOCKED` — a safety/authority precondition failed before any mutation.
- `STALE_EVIDENCE` — identity, branch, HEAD, or changed-path evidence is stale
  or mismatched.
- `DECISION_REJECTED` — the controller decision is not `APPROVE`.
- `PUBLICATION_FAILED` — commit or push verification failed after local mutation.

### 16.7 Audit and artifacts

Every finalization attempt appends:

- a bounded JSON Lines record with `mode: "finalize"` to
  `.agent_runner/audit/runner.jsonl`, and
- a dedicated finalization artifact line to
  `.agent_runner/finalize/finalize.jsonl` on successful completion.

Both records contain only safe metadata: task id/filename, branch, pre/post HEAD,
decision path, bundle path, staged/changed paths, lifecycle states, commit SHA,
push command/result, terminal status, and bounded messages. They exclude full task
bodies, worker transcripts, credentials, environment dumps, secrets, customer
business data, and unrestricted command output.

### 16.8 Safety guarantees

- `main` is never pushed, committed to, or otherwise mutated.
- Force push, refspec rewriting, tag creation, delete, and merge commits are
  impossible through this command.
- Staging is exact and re-verified; scope mismatch stops before commit.
- A dirty working tree after commit blocks push.
- An upstream mismatch (e.g. feature branch tracking `origin/main`) blocks push.
- Preview mode changes no lifecycle state, index, HEAD, or remote state.
- Apply mode stops at the first failed gate and reports the exact blocking
  condition.

---

## 17. End-to-End Controller Orchestration (TASK-021)

### 17.1 Purpose

TASK-021 adds a thin, provider-neutral coordinator over the existing governed
stages.  It removes stage-by-stage command and artifact couriering without
creating a new lifecycle, controller, verification, or publication authority.

```text
owner goal -> DRAFT generation -> task approval gate -> auto-pipeline/repair
           -> implementation decision gate -> TASK-020 finalization -> pushed
```

The implementation lives in `advancore/agent_runner/orchestration.py` and is
exposed through `python -m advancore.agent_runner orchestrate`.  Preview is the
default; `--apply` is required for planner/worker launch, checkpoint/task writes,
lifecycle changes, controller dispatch, or finalization.

### 17.2 State and checkpoints

One run owns one bounded goal and at most one generated task.  Its versioned
checkpoint is atomically written under ignored `.agent_runner/orchestration/`
and correlates the task, branch/HEAD, changed paths, review bundle, handoff,
decision, auto result, finalization result, adapters, and bounded attempt counts.

Resume reloads the checkpoint's provider selections and budgets, then
revalidates authoritative files and current Git evidence.  A checkpoint alone
is never authority.  Completed phases are not repeated, conflicting artifacts
fail closed, and verified publication is terminal and idempotent.

### 17.3 Authority-preserving phase flow

- TASK-019 remains the only DRAFT generator.
- DRAFT waits for a valid controller/owner `DRAFT -> READY` transition.
- TASK-017/TASK-018 remain the implementation, verification, and repair path.
- `READY_FOR_APPROVAL` creates review evidence only.
- Existing handoff/adapter/transport and decision records remain the controller
  boundary.
- Controller REWORK uses the valid sequence
  `READY/REWORK -> IN_PROGRESS -> REVIEW -> REWORK`, with worker and controller
  attribution kept distinct and one bounded orchestration rework cycle.
- Controller APPROVE alone may enter TASK-020 finalization.
- Success requires TASK-020 `PUSHED` evidence for the same non-`main` branch.

### 17.4 Permanent AdvanCore versus local operator

AdvanCore permanently owns phase sequencing, checkpoint integrity, evidence
correlation, resume/idempotency, authority validation, bounded retries, and
fail-closed terminal reporting.

Codex desktop, a human, or another approved local client may launch, monitor,
and resume the CLI and present exceptions.  Those clients do not replace
`agent_runner`, do not gain approval authority from operating the process, and
are not runtime dependencies.  No Codex SDK, ChatGPT/OpenAI API, desktop
automation, or vendor credential management is embedded in AdvanCore.

### 17.5 Safety guarantees

- Preview launches no model and writes no task, checkpoint, handoff, decision,
  or publication artifact.
- Resume uses persisted adapters/budgets rather than silently accepting new CLI
  defaults.
- Worker output and passing tests cannot create task or publication authority.
- Unknown, stale, malformed, duplicate, conflicting, or unsafe evidence fails
  closed with one exact next action.
- The coordinator never directly stages, commits, pushes, merges, deploys,
  force-pushes, manages credentials, or targets `main`.

---

## 18. Governed Worker Fallback Boundary (TASK-022)

An orchestration run may explicitly select one primary implementation worker
and at most one fallback from the code-owned adapter registry. There is no
fallback by default. The fallback is attempted only for a recognised provider
availability failure (missing executable, quota/capacity, or unavailable
authentication) and only when branch, HEAD, index, worktree, and remotes remain
unchanged. Unknown failures or any ambiguous mutation stop the run.

The local Codex adapter uses fixed argv, an ephemeral session, workspace-write
sandboxing, and non-interactive approval denial. It cannot accept arbitrary
commands, sandbox bypasses, extra writable roots, cloud execution, web search,
or credentials from task or CLI input. Kimi, Kimi-Swarm, Codex, and future
approved adapters remain implementation workers only; controller decisions and
TASK-020 publication authority stay separate.

Fallback selection and the terminal worker are included as bounded checkpoint
and audit evidence. Raw worker transcripts, environment dumps, and credentials
are not persisted in fallback artifacts.

---

## 19. Worker Fallback Operational Validation (TASK-023)

TASK-023 validates the TASK-022 boundary at the real adapter/subprocess layer
without a live provider. Integration fixtures create temporary Git repositories
and place fake `kimi`, `codex`, and pass-through `git` executables on an isolated
`PATH`. This proves the production Kimi-Swarm and Codex argv, subprocess return
handling, Git-integrity snapshots, fallback classification, downstream pytest,
diff-check, scope verification, report formatting, and persisted auto evidence.

The validation demonstrates:

- a clean quota/capacity failure invokes exactly the explicitly selected Codex
  fallback and then runs the existing verification path;
- unknown failures and branch, HEAD, index, worktree, or remote mutations stop
  after the primary worker;
- a failed fallback is terminal, so a third worker cannot be chained;
- CLI omission means no fallback, while duplicate, unknown, or `dry-run`
  combinations fail closed; and
- reports and artifacts retain primary, classification, fallback, and terminal
  identity while excluding raw transcripts and credential-like fixture values.

The permanent/local responsibility split is unchanged. AdvanCore's
`agent_runner` permanently owns adapter registration, policy validation,
fallback eligibility, integrity checks, verification, bounded persistence, and
terminal reporting. A local operator, Codex desktop, or another approved client
may select an already-approved policy, launch or resume it, and surface
exceptions. The client does not become a controller and cannot bypass the
TASK-020 approval and publication gates. See
`docs/runbooks/WORKER_FALLBACK.md` for the operator procedure and
`docs/decisions/ADR-023-worker-fallback-operational-validation.md` for the
validation decision.

---

## 20. Read-Only Orchestration Exception Inbox (TASK-027)

`advancore.agent_runner.orchestration_inbox` projects unresolved local
checkpoints into a bounded exception list. The CLI discovers runs without a
caller-supplied ID:

```bash
.venv/bin/python -m advancore.agent_runner orchestration-inbox
.venv/bin/python -m advancore.agent_runner orchestration-inbox --json
.venv/bin/python -m advancore.agent_runner orchestration-inbox --run ORCH-<id>
```

Discovery is deterministic and limited to JSON checkpoint candidates under
`.agent_runner/orchestration/`. Every candidate is revalidated against the
current checkpoint schema, filename/run ID, authoritative task file, bounded
artifact paths and cross-links, current branch/HEAD/path fingerprint, and
terminal publication evidence. A verified, idempotent `PUBLISHED` run is
excluded. Missing, malformed, conflicting, unsafe, unreadable, or stale
evidence is retained as a fail-closed exception rather than skipped.

Entries are ordered by classification urgency, checkpoint timestamp, and run
ID. They expose only run and task identity/title, phase/status, a bounded
reason, bounded evidence references, whether an owner decision is required,
and one exact preview command. The `advancore-orchestration-inbox-v1` JSON
schema is stable and contains no goal/task bodies, prompts, transcripts, raw
worker output, environment, or credentials.

The inbox performs read operations only. It does not normalize checkpoints,
append audit records, change lifecycle state, create handoffs or decisions,
launch processes other than read-only Git inspection, resume workers, or
delegate publication. Its preview command omits `--apply`, and its
classification never implies approval or recovery.

Codex desktop, a phone-oriented presentation, or another local client may
render this JSON and relay an explicitly selected command. AdvanCore remains
the provider-neutral owner of validation and governance classification. The
presentation client is optional, creates no authority, and must not reinterpret
an entry as approval, a lifecycle transition, or permission to publish.

---

## 21. Explicit completed-run reconciliation (TASK-030)

An operator may explicitly recognize an already-successful publication whose
orchestration checkpoint remained stale:

```bash
.venv/bin/python -m advancore.agent_runner reconcile-completed-run ORCH-<id>
.venv/bin/python -m advancore.agent_runner reconcile-completed-run ORCH-<id> --apply
```

This is a preview-first recovery command, not an alternate finalization path.
It resolves exactly the named checkpoint and requires the authoritative task
to be `APPROVED`, a named current non-`main` branch matching the checkpoint,
and identical finalized local and `refs/remotes/origin/<branch>` tips. It reads
that tracking ref locally and does not fetch or contact a remote. Only
`--apply` may update the checkpoint.

The command resolves one exact controller/owner `APPROVE` decision from the
canonical decision directory linked to the checkpoint review bundle and one
exact `PUSHED` record from the canonical finalization artifact. The record's
pre-commit HEAD must equal the bundle HEAD; its post/commit HEAD must equal the
synchronized local/origin tip. Persisted checkpoint decision/finalization paths
must match when present, but an interrupted checkpoint is not required to have
recorded evidence created later.
Missing, malformed, unauthorized, stale, conflicting, duplicated, or ambiguous
evidence fails closed before mutation.

On success, the runner atomically replaces only the named checkpoint, preserves
its existing history and evidence references, appends one bounded
`reconciliation_evidence` entry, and records the already-proven `PUBLISHED`
outcome. It does not invoke a worker or finalizer and never stages, commits,
pushes, fetches, merges, changes branches, edits task/controller/review/
finalization artifacts, or weakens ordinary orchestration resume validation.
