# TASK-027 — Read-Only Orchestration Exception Inbox

STATUS: APPROVED

## Objective

Add one read-only, fail-closed view of unresolved orchestration exceptions so a
local operator or phone-based owner can see what genuinely requires attention
without discovering run IDs, reading long logs, or triggering mutations.

## Business context

TASK-021 through TASK-026 provide bounded orchestration, resilient workers,
explicit owner decision intake, and end-to-end acceptance. The remaining daily
friction is exception discovery: checkpoints and reports contain the necessary
state, but an operator must know which run to inspect and translate its status
into an owner-facing action.

This capability belongs permanently in AdvanCore as a provider-neutral,
read-only projection. Codex desktop or another client may display the result,
but must not invent its own governance classification or become required.

## In scope

1. Add a focused exception-inbox module that discovers versioned orchestration
   checkpoints under the existing ignored directory.
2. Revalidate every candidate against authoritative checkpoint schema, task,
   evidence paths, branch/HEAD where applicable, and terminal/idempotent state.
3. Emit bounded entries only for unresolved states such as task approval,
   implementation decision, owner decision, rework/exhaustion, non-repairable,
   stale evidence, blocked, failed, timeout, or cancellation.
4. Exclude verified `PUBLISHED` runs and safely completed/idempotent states.
5. Distinguish action-required, operator-investigation, and stale/invalid
   evidence without inferring approval or recovery.
6. Each entry may contain only run ID, task ID/title, phase/status, bounded
   reason, evidence references, owner-decision-required flag, and one exact
   preview/resume command. No prompts, transcripts, raw output, credentials,
   environment, or task bodies.
7. Provide deterministic ordering by urgency then bounded checkpoint timestamp/
   run ID; do not depend on filesystem enumeration order.
8. Add a CLI command equivalent to `orchestration-inbox [--json] [--run <id>]`.
   Human output is concise; JSON uses a versioned stable schema.
9. The command must be strictly read-only: no checkpoint normalization, audit
   append, lifecycle transition, handoff, decision, Git, worker, or publication.
10. Malformed, conflicting, unreadable, or unsafe evidence becomes a bounded
    fail-closed inbox entry rather than being silently skipped.
11. Document how Codex desktop/phone presentation consumes this view while
    AdvanCore remains independently governed and vendor-neutral.

## Out of scope

- Notifications, polling daemons, automations, webhooks, servers, remote APIs, or GUIs.
- Creating or applying owner/controller decisions.
- Natural-language action inference.
- Worker launch, retry, resume, finalization, merge, deployment, or `main`.
- Authentication, credentials, or production/customer data.

## Allowed changed-file scope

1. `advancore/agent_runner/orchestration_inbox.py` (new)
2. `advancore/agent_runner/__main__.py`
3. `advancore/agent_runner/__init__.py`
4. `tests/test_orchestration_inbox.py` (new)
5. `docs/architecture/AGENT_RUNNER.md`
6. `docs/decisions/ADR-027-read-only-orchestration-exception-inbox.md` (new)
7. `tasks/TASK-027-read-only-orchestration-exception-inbox.md`

No other file may change.

## Acceptance criteria

1. Unresolved runs are discovered without a caller-supplied run ID.
2. Published/complete runs are excluded.
3. Malformed or stale evidence is surfaced fail closed.
4. Ordering and JSON schema are deterministic.
5. Human output contains one concise next action per entry.
6. Read-only tests prove no file, Git, lifecycle, audit, decision, or process mutation.
7. No authority is created and no approval is inferred.
8. Full repository test suite passes and exact changed paths stay within scope.

## Required verification

```bash
.venv/bin/python -m pytest tests/test_orchestration_inbox.py -v
.venv/bin/python -m pytest tests/ -v
git diff --check
```

## Owner decisions

The owner authorized continued bounded development while available by phone.
The exception inbox is read-only and does not spend or replace owner authority.

## Completion report

### Implemented

- Added deterministic, read-only discovery and fail-closed revalidation of
  local orchestration checkpoints.
- Added bounded action-required, operator-investigation, and
  stale-or-invalid-evidence classifications with stable JSON and concise human
  output.
- Added `orchestration-inbox [--json] [--run <id>]` without mutation authority.
- Added focused read-only, malformed/stale, publication, ordering, schema, and
  CLI tests plus architecture and decision documentation.

### Files changed

- `advancore/agent_runner/orchestration_inbox.py`
- `advancore/agent_runner/__main__.py`
- `advancore/agent_runner/__init__.py`
- `tests/test_orchestration_inbox.py`
- `docs/architecture/AGENT_RUNNER.md`
- `docs/decisions/ADR-027-read-only-orchestration-exception-inbox.md`
- `tasks/TASK-027-read-only-orchestration-exception-inbox.md`

### Database changes

- None.

### Tests and results

- `.venv/bin/python -m pytest tests/test_orchestration_inbox.py -v` — 6 passed.
- `.venv/bin/python -m pytest tests/ -v` — 601 passed.
- `git diff --check` — passed.

### Assumptions

- A `PUBLISHED` checkpoint is safely excludable only when its terminal phase,
  status, push flag, commit, finalization reference, and completed finalization
  phase are present and all other checkpoint evidence revalidates.
- Checkpoint timestamp ordering is oldest first within each urgency class so
  long-waiting exceptions remain visible.

### Risks / unresolved issues

- No notification or remote presentation is included; clients must invoke or
  render the local read-only view on demand.
- Existing artifact loaders are reused where available; goal-task, auto, and
  finalization references are containment/existence checked because those
  modules do not expose equivalent single-artifact read validators.

### Decisions required

- Independent review and owner approval of TASK-027 completion remain required.

### Recommended next step

- Review the implementation and verification evidence, then perform any
  authorized lifecycle/finalization action separately. Do not infer approval
  from this completion report.
