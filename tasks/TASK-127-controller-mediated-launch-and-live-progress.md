# TASK-127 — Controller-Mediated Launch and Live Progress

STATUS: APPROVED

## Objective

Connect the decoupled local console to AdvanCore's existing orchestration state
machine so the owner can preview, explicitly start, monitor and resume governed
work without giving the browser direct worker, database, Git or publication
authority.

## Business context

TASK-126 deliberately stopped at a dry-run Owner Goal preview. That protects the
existing system but does not yet remove the owner’s stage-by-stage courier work.
This task adds a narrow controller bridge: the browser requests an action,
FastAPI passes only a fixed bounded configuration to the controller, and the
controller delegates worker execution to `agent_runner` using the existing
Kimi-Swarm → Gemini → Codex route.

## Facts

- TASK-126 provides the static console and loopback-only FastAPI boundary.
- `run_orchestration()` already owns task generation, authority gates, worker
  routing, verification, repair, controller review and feature-branch
  finalization.
- `OwnerAction` already provides phase-bound owner approval/block/rework intake.
- Orchestration checkpoints are ignored local coordination evidence, not source
  of truth or authority.
- UI colours, controls and animations remain replaceable presentation details.

## In scope

- Fixed-policy orchestration preview and explicit launch endpoints.
- An explicit resume endpoint for an existing run.
- Phase-bound owner-action endpoints that delegate to existing `OwnerAction`
  intake; no new approval model.
- A single-active-job local coordinator preventing concurrent repository runs.
- Read-only job and checkpoint projections.
- Server-Sent Events for bounded live progress updates across page sessions.
- A process-lifetime anti-CSRF action token and strict loopback-origin checks on
  every mutating endpoint.
- UI controls for preview, start, resume and exact controller-gate actions.
- Fixed Kimi-Swarm → Gemini → Codex implementation routing through unattended
  orchestration policy; the browser cannot select or reorder workers.
- Focused tests and architecture documentation.

## Out of scope

- Direct browser access to a worker adapter, shell command, subprocess or Git.
- New database endpoints, schema changes, Alembic migrations or operational
  data writes by the API.
- Automatic approval, inferred owner consent or approval based on passing tests.
- Publication without a separately valid exact-phase owner/controller APPROVE.
- Main-branch publication, merge, deployment, credentials or billing.
- Cancellation or force-termination of a running worker.
- Remote access, authentication accounts, hosted queues or multi-run concurrency.
- Changes to `advancore/agent_runner/**` governance implementation.

## Allowed changed-file scope

- `advancore/api/**`
- `frontend/**`
- `tests/test_api_orchestration.py`
- `docs/architecture/DECOUPLED_LOCAL_CONSOLE.md`
- `tasks/TASK-127-controller-mediated-launch-and-live-progress.md`

## Database impact

None. The API adds no database-writing route and changes no schema or migration.
Any future task containing an authorised database change remains subject to its
task specification, controller approval and existing migration rules.

## Acceptance criteria

- [x] Preview invokes orchestration with `apply=False` and performs no mutation.
- [x] Start requires a valid local action token, explicit confirmation and an
      approved loopback Origin.
- [x] Browser input cannot select workers, controller adapters, budgets, paths,
      shell commands, publication targets or apply flags.
- [x] New runs use the fixed governed planner/worker policy and existing
      Kimi-Swarm → Gemini → Codex implementation route.
- [x] At most one orchestration job can run at a time.
- [x] Owner actions are accepted only through the existing phase-bound
      `OwnerAction` model and `run_orchestration()` validation.
- [x] Task approval may launch a worker only after the existing DRAFT → READY
      authority transition succeeds.
- [x] Implementation approval may publish only through existing controller
      decision and finalization gates on a non-main feature branch.
- [x] Progress payloads contain bounded status/evidence metadata, not goal text,
      prompts, transcripts, credentials or environment values.
- [x] Live progress survives browser refresh while the local server remains up.
- [x] Server restart relies on existing checkpoint resume rather than inventing
      completed state.
- [x] UI customization remains isolated from controller and database logic.
- [x] Focused and full tests pass.
- [x] Completion report is produced.

## Test requirements

- Fixed-policy preview/start configuration tests.
- Local token, Origin, explicit-confirmation and unknown-field rejection tests.
- Single-active-job concurrency test.
- Phase-bound action and resume delegation tests.
- Job/checkpoint projection redaction tests.
- SSE progress completion test.
- Frontend contract checks for no direct worker invocation.
- Full pytest suite, `git diff --check` and zero migration/core-path diff.

## Constraints

- The API may import only public orchestration models and functions; it must not
  copy or reinterpret lifecycle, worker-routing, controller or finalization
  logic.
- The owner goal is bounded by the existing 2,000-character limit.
- Mutating requests must use JSON, an exact process-lifetime action token and an
  allowed loopback Origin.
- Errors returned to the browser must be bounded and must not contain tracebacks,
  environment dumps or credential-bearing URLs.
- Background execution is single-process local convenience; durable truth
  remains in task files, governance artifacts, Git and orchestration checkpoints.

## Owner decisions

None. The owner has approved controller-mediated launch and live progress while
retaining controller gates for database changes, approvals and publication.

## Completion report

### Implemented

- Added a fixed-policy adapter over the existing `run_orchestration()` entry
  point; lifecycle and worker routing rules were not copied into the API.
- Added explicit start, resume and phase-bound owner-action requests protected
  by loopback Origin checks, a process-lifetime action token, strict JSON
  contracts and exact confirmation booleans.
- Added a bounded single-active-job coordinator, current-job recovery and SSE
  progress without exposing goal text or worker prompts.
- Added Owner Goal preview/start, live progress, resume and exact controller
  action controls to the decoupled console.
- Kept UI design tokens, layout and animations in the static frontend layer.

### Files changed

- `advancore/api/app.py`
- `advancore/api/schemas.py`
- `advancore/api/orchestration_service.py`
- `advancore/api/routes/orchestration.py`
- `frontend/app.js`
- `frontend/index.html`
- `frontend/styles.css`
- `tests/test_api_orchestration.py`
- `docs/architecture/DECOUPLED_LOCAL_CONSOLE.md`
- `tasks/TASK-127-controller-mediated-launch-and-live-progress.md`

### Database changes

None.

### Tests and results

- Focused API/controller tests: `19 passed`.
- Full project suite: `1272 passed, 2 skipped`.
- `git diff --check`: passed.
- JavaScript syntax check: passed.
- Browser visual QA: desktop and 390 px phone layout passed; no horizontal
  overflow; preview reported no mutations and no worker launch.
- One upstream FastAPI/Starlette TestClient deprecation warning remains; it is
  unrelated to TASK-127 behavior.

### Assumptions

- The FastAPI process remains local and loopback-only.
- One active development run is sufficient for the local owner console.

### Risks / unresolved issues

- A server restart ends its in-memory live stream; the existing checkpoint can
  still be inspected and explicitly resumed.
- The bridge intentionally has no force-cancel control. A running worker must
  stop through existing controller/runner behavior.

### Decisions required

None for this local feature-branch commit. Any push, PR, merge or deployment
remains a separate governed action.

### Recommended next step

Independently review the committed TASK-127 changes. Any later PR must target
`projects-lifecycle-recovery`, never `main`.
