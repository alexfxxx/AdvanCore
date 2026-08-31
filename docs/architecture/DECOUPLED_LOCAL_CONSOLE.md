# Primary Local Console

## Status

TASK-126 provides the additive presentation scaffold. TASK-127 adds a narrow
controller-mediated launch and progress bridge. TASK-168 provides the compact
customizable workspace. TASK-169 designates this FastAPI-served interface as
the primary AdvanCore app. Streamlit remains only as temporary admin/editing
support while its remaining forms transfer.

## Boundary

```text
Browser HTML/CSS/JavaScript
        |
        | read requests, explicit Owner Goal or exact owner action
        v
FastAPI loopback presentation adapter
        |
        | fixed policy request; never a browser-selected worker/command
        v
AdvanCore controller -> agent_runner -> approved worker route
```

The browser is an untrusted presentation client. It has no database session,
shell access, worker adapter, Git client, publication target or deployment
capability. It can submit an exact phase-bound owner action, but existing
orchestration code remains solely responsible for validating and applying it.

## Initial endpoints

- `GET /api/status` returns bounded readiness booleans and states. It never
  returns environment values, connection strings or credentials.
- `GET /api/projects` reads through `ProjectService` and `ProjectRepository`.
- `GET /api/knowledge` reads through `KnowledgeService` and
  `KnowledgeItemRepository`.
- `POST /api/owner-goals/preview` invokes existing goal-to-task generation with
  `DryRunWorkerAdapter` and `execute=False`. It launches no planner and writes no
  task file.
- `WS /ws/transcription` reports that voice is disabled and accepts no audio.

## Controller-mediated endpoints

- `GET /api/session` issues a process-lifetime anti-CSRF action token. The
  response is `no-store`; the frontend keeps the token only in memory.
- `POST /api/orchestrations/preview` runs the existing orchestration in
  `apply=False` mode and returns its bounded projection.
- `POST /api/orchestrations` submits an explicitly confirmed new run.
- `POST /api/orchestrations/{run_id}/resume` resumes an existing checkpoint.
- `POST /api/orchestrations/{run_id}/actions` submits one exact existing
  `OwnerAction`; it does not create a second approval model.
- `GET /api/orchestration-jobs/{job_id}` and its `/events` Server-Sent Events
  stream expose bounded live state without goal text, prompts or credentials.
- `GET /api/orchestration-jobs/current` restores the active or most recent
  bounded job snapshot after a page refresh in the same server process.
- `GET /api/orchestrations/{run_id}` provides a bounded checkpoint projection.

Every mutating request requires both an allow-listed loopback `Origin` and the
process-lifetime token. Unknown JSON fields, coerced confirmation values and
malformed run identifiers are rejected. Only one repository orchestration job
may run at once.
Process-local job history is capped at 50 bounded records.

New runs use a server-fixed configuration. The browser cannot set workers,
controller adapters, timeouts, repair budgets, paths, branches or apply flags.
The existing unattended worker policy retains Kimi-Swarm first and Codex as its
approved fallback; the existing worker route supplies Gemini as the intermediate
candidate where configured. Resumed runs recover their policy from the durable
checkpoint rather than accepting browser overrides.

Task approval, implementation review, database effects and safe feature-branch
publication continue through the existing controller and `agent_runner`
authority boundaries. A green test result or completed worker job is never
treated as approval. `main`, merge and deployment authority are not exposed.

Database reads use a rollback-only session. No API route is authorised to
commit a transaction.

## Presentation customization

Colours, spacing, buttons and animations are isolated in `frontend/styles.css`
and use CSS custom properties as design tokens. Page interaction remains in
separate vanilla-JavaScript files. Future owner-selectable themes or animation
preferences can therefore change presentation without altering PostgreSQL,
business services, controller policy or `agent_runner` authority.

TASK-137 adds three fixed, allow-listed themes, two panel shapes and a reduced
motion choice. The validated selection is stored only in browser
`localStorage`; arbitrary CSS, HTML and remote themes are not accepted.

## Read-only operations

- `GET /api/fleet` returns existing companies and vehicles, with optional
  company, approved vehicle-type and exact-capacity filters.
- `GET /api/dispatch?service_date=YYYY-MM-DD` uses the existing dispatch-board
  service to project recorded trips, assignments, conflicts and available
  resources for one date.
- `GET /api/fuel/intelligence` reports calculations derived only from recorded
  fuel entries.
- `GET /api/fuel/market-benchmark` returns a repository-held, dated Singapore
  gross pump-price reference. It never scrapes during app startup and never
  writes the reference into the operational database.

All database-backed reads use rollback-only sessions. The operational API has
no POST, PUT, PATCH or DELETE route.

## Local startup

After installing the pinned project requirements in an isolated environment,
the normal launcher starts PostgreSQL, applies already-approved migrations, and
starts both local interfaces:

```bash
./scripts/start-advancore.sh
```

Open `http://127.0.0.1:8000` as the primary AdvanCore app. Use
`http://127.0.0.1:8501` only for temporary admin/editing workflows. Run
`./scripts/check-local-interfaces.py` for a bounded readiness check. Binding to
`0.0.0.0` remains outside scope.

The static frontend is served by FastAPI on the same origin. Explicit CORS
origins exist only for bounded loopback development ports; wildcard origins
are not used.

## Voice-provider future boundary

The browser `MediaRecorder` hook is disabled and discards chunks in memory.
`MediaRecorder` commonly emits compressed browser formats, while Gemini Live
Transcription requires raw 16-bit PCM audio. A later governed task should use
an `AudioWorklet` or controlled server conversion, plus a replaceable
transcription-provider interface.

No provider credential may be embedded in JavaScript. If a browser connects
directly to a provider, the backend must issue a constrained short-lived token.
No audio or transcript is stored by default. A final transcript remains
editable and requires explicit owner submission before it enters the
controller workflow.

## Deliberately absent direct browser capabilities

- Direct task lifecycle mutation outside existing controller actions
- Direct worker execution, worker selection or fallback routing
- Direct database writes or migrations
- Direct commit, push, PR, merge or deployment
- Gemini connection, credential handling or billing
- Remote access or authentication

The controller may perform only operations already authorised by its governed
task, current lifecycle phase and exact owner decision. New capabilities still
require a separate governed task and owner decision.
