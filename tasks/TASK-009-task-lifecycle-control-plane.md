# TASK-009 — Task Lifecycle Control Plane

STATUS: REVIEW

## Objective

Introduce an explicit task-state model and authority-aware transition helper for the AdvanCore Agent Runner so task lifecycle changes become controlled, validated, and auditable instead of being edited ad hoc.

This task is about workflow state only. It does not add automatic commit/push/merge authority.

## Context

The repository currently defines these task states in `tasks/README.md`:

- DRAFT
- READY
- IN_PROGRESS
- REVIEW
- REWORK
- APPROVED
- BLOCKED

TASK-005 through TASK-008 established a fail-closed runner, real Kimi execution, post-worker Git verification, explicit approval gating, and local audit records. The next control gap is task lifecycle management.

## Required state machine

Use the existing repository states and enforce only these normal transitions:

- DRAFT -> READY
- READY -> IN_PROGRESS
- IN_PROGRESS -> REVIEW
- REVIEW -> APPROVED
- REVIEW -> REWORK
- REWORK -> IN_PROGRESS
- any non-final working state -> BLOCKED when a dependency/decision prevents progress
- BLOCKED -> READY or REWORK only when explicitly released by an authorized controller/reviewer

Do not invent extra statuses in this task.

## Authority model

Model transition authority explicitly.

### Worker authority

A worker may request/report only:

- READY -> IN_PROGRESS
- REWORK -> IN_PROGRESS
- IN_PROGRESS -> REVIEW

A worker must not approve its own work.

### Controller/reviewer authority

A controller/reviewer may perform:

- DRAFT -> READY
- REVIEW -> APPROVED
- REVIEW -> REWORK
- transitions to/from BLOCKED as defined above

### Owner authority

Owner authority includes controller/reviewer transitions and remains required for any higher-impact decision already gated elsewhere. This task does not add new owner-only product or business rules.

## In scope

1. Add a small lifecycle module under `advancore/agent_runner/`.
2. Represent task states and actor/authority roles explicitly using simple Python types/enums/dataclasses where appropriate.
3. Implement a pure validation function that answers whether a requested transition is allowed for a given actor role.
4. Implement a narrow task-status update helper that:
   - reads a known task file,
   - validates current status,
   - validates requested transition and actor authority,
   - updates only the single `STATUS:` line,
   - preserves all other task content byte-for-byte except unavoidable newline normalization if required,
   - refuses malformed or ambiguous task files.
5. Add a runner/CLI command for lifecycle transition requests, for example a dedicated `status` or `transition` subcommand.
6. Default behavior must be dry-run / preview only.
7. Actual task-file mutation must require an explicit flag such as `--apply`.
8. The command must show:
   - task ID,
   - current state,
   - requested state,
   - actor role,
   - whether the transition is permitted,
   - whether the change was previewed or applied.
9. Record lifecycle transition attempts in the existing local audit trail using safe metadata only.
10. Update `tasks/README.md` to document the authoritative state machine and actor responsibilities.
11. Update `docs/architecture/AGENT_RUNNER.md` and add an ADR for the lifecycle-control decision.
12. Add deterministic tests for allowed/denied transitions, malformed files, dry-run behavior, applied mutation, and audit metadata.
13. Run the full pytest suite.
14. Fill in this task completion report and stop without committing or pushing.

## Safety constraints

- Do not add automatic Git commit, push, merge, branch-switch, or remote-sync behavior.
- Do not allow the worker to transition REVIEW -> APPROVED.
- Do not allow task-file content to supply executable commands.
- Do not modify task body text other than the `STATUS:` line.
- Do not mutate multiple task files in one invocation.
- Do not change database models, migrations, ERP modules, commercial rules, compliance rules, or production configuration.
- Do not touch `main`.
- Existing runner execution safety checks must remain intact.

## Database impact

None.

## Acceptance criteria

- [ ] Explicit task-state representation exists.
- [ ] Explicit actor-role representation exists.
- [ ] Allowed transition matrix matches this task specification.
- [ ] Worker cannot self-approve.
- [ ] Controller/reviewer can approve or request rework from REVIEW.
- [ ] Dry-run is the default for lifecycle changes.
- [ ] Applying a transition requires an explicit flag.
- [ ] Only the `STATUS:` line changes on a valid applied transition.
- [ ] Invalid/unauthorized transitions fail closed.
- [ ] Malformed/ambiguous task status fails closed.
- [ ] Lifecycle attempts are locally audited with safe metadata.
- [ ] `tasks/README.md` documents the authoritative lifecycle.
- [ ] No commit/push/merge capability is added.
- [ ] No database or ERP changes are made.
- [ ] Full pytest suite passes.
- [ ] Completion report is produced.

## Test requirements

At minimum test:

1. DRAFT -> READY allowed for controller/reviewer, denied for worker.
2. READY -> IN_PROGRESS allowed for worker.
3. IN_PROGRESS -> REVIEW allowed for worker.
4. REVIEW -> APPROVED denied for worker, allowed for controller/reviewer.
5. REVIEW -> REWORK allowed for controller/reviewer.
6. REWORK -> IN_PROGRESS allowed for worker.
7. Invalid skipped transitions are denied.
8. BLOCKED transitions follow the authority rules above.
9. Dry-run does not modify the file.
10. `--apply` changes only the status line.
11. Malformed or duplicate STATUS lines fail closed.
12. Audit metadata captures task ID, previous status, requested status, actor role, allowed/denied result, and applied/preview mode without storing task body content.
13. Existing runner and non-runner tests remain passing.

Run:

```bash
.venv/bin/python -m pytest tests/ -v
```

## Out of scope

- Automatic staging/commit/push/merge.
- Automatic remote task synchronization.
- GitHub API task mutation by the local runner.
- Automatic reviewer approval.
- Multi-task batch transitions.
- ERP/business feature development.
- Database work.
- Production deployment.

## Owner decisions

None required to begin.

## Completion report

### Implemented

- Added `advancore/agent_runner/lifecycle.py` with explicit `TaskStatus` and
  `ActorRole` enums, a pure `is_transition_allowed()` validator, and the
  `transition_task()` helper.
- Implemented authority-aware transition rules per the task specification,
  including BLOCKED transitions and the worker self-approval prohibition.
- Made task-status updates dry-run by default; mutation requires `--apply`.
- Ensured only the single `STATUS:` line is rewritten; the task body is
  preserved, and missing/duplicate STATUS lines fail closed.
- Extended `advancore/agent_runner/audit.py` with a lifecycle audit payload so
  every transition attempt is recorded in the existing `.agent_runner/audit/runner.jsonl`.
- Added a `transition` subcommand to `advancore/agent_runner/__main__.py`.
- Updated `tasks/README.md` with the authoritative state machine, actor
  responsibilities, and CLI examples.
- Updated `docs/architecture/AGENT_RUNNER.md` with the lifecycle module, state
  model, CLI usage, and threat boundary.
- Added `docs/decisions/ADR-005-task-lifecycle-control-plane.md`.
- Added `tests/test_agent_runner_lifecycle.py` covering allowed/denied
  transitions, dry-run, applied mutation, malformed files, and audit metadata.
- Ran the full pytest suite; all tests pass.
- Used the new CLI to move this task from READY → IN_PROGRESS → REVIEW.

### Files changed

- `advancore/agent_runner/__init__.py`
- `advancore/agent_runner/__main__.py`
- `advancore/agent_runner/audit.py`
- `advancore/agent_runner/lifecycle.py` (new)
- `docs/architecture/AGENT_RUNNER.md`
- `docs/decisions/ADR-005-task-lifecycle-control-plane.md` (new)
- `tasks/README.md`
- `tasks/TASK-009-task-lifecycle-control-plane.md`
- `tests/test_agent_runner_lifecycle.py` (new)

### Database changes

None.

### Tests and results

```bash
.venv/bin/python -m pytest tests/ -v
```

Result: **121 passed** (79 existing + 42 new).

### Assumptions

- `controller` in `ActorRole` represents both controller and reviewer authority.
- Owner authority includes controller/reviewer transitions and the worker
  transitions, so an owner is not more restricted than the roles it supersedes.
- Lifecycle audit records reuse the existing `.agent_runner/audit/runner.jsonl`
  file and contain only safe metadata (no task body).
- The `transition` CLI requires a Git repository snapshot for audit metadata,
  consistent with the runner's existing Git introspection.

### Risks / unresolved issues

- The lifecycle helper validates transitions only when invoked; it does not
  prevent direct manual edits to task files. Governance and review remain the
  primary enforcement.
- `parse_task()` still tolerates duplicate `STATUS:` lines by taking the first
  match; the lifecycle helper now rejects duplicates, but a future task may want
  to tighten `parse_task()` as well.
- No remote/GitHub task-status synchronization is implemented.

### Decisions required

None.

### Recommended next step

Human review of the implementation and documentation. If approved, the changes
may be committed and pushed. A future task could optionally integrate lifecycle
updates into `execute()` (e.g. READY → IN_PROGRESS at start and
IN_PROGRESS → REVIEW on successful completion), gated by the same authority
model.

### `git status --short`

```
 M advancore/agent_runner/__init__.py
 M advancore/agent_runner/__main__.py
 M advancore/agent_runner/audit.py
 M docs/architecture/AGENT_RUNNER.md
 M tasks/README.md
 M tasks/TASK-009-task-lifecycle-control-plane.md
?? advancore/agent_runner/lifecycle.py
?? docs/decisions/ADR-005-task-lifecycle-control-plane.md
?? tests/test_agent_runner_lifecycle.py
```
