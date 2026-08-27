# TASK-126 — Decoupled API and Frontend Scaffold

STATUS: COMPLETE

## Objective

Add a reversible local FastAPI and static-browser interface beside the existing
Streamlit application so future interfaces are not constrained by Streamlit,
while preserving AdvanCore's existing controller and `agent_runner` authority
boundaries.

## Business context

The owner needs a more flexible visual and eventual voice interface without
rewriting the operational core or allowing browser input to bypass governance.
The new interface must remain an additive presentation layer until it has been
independently verified and deliberately adopted.

## Facts

- PostgreSQL remains the operational source of truth.
- GitHub remains the source of truth for code and governed task artifacts.
- `agent_runner` remains the authority boundary.
- The existing Streamlit application remains available during the transition.
- Voice and text input are untrusted Owner Goal text, not execution authority.

## In scope

- A thin root `main.py` FastAPI entry point.
- A presentation-independent `advancore.api` package.
- Read-only system-status, project and Knowledge endpoints.
- An Owner Goal preview endpoint using the existing goal-to-task controller in
  dry-run mode only.
- An explicitly disabled voice WebSocket hook for later transcription-provider
  integration.
- A static HTML, CSS and vanilla-JavaScript control console.
- Loopback-only startup and explicit local-development CORS origins.
- Focused API, CORS, frontend and governance-boundary tests.
- Architecture and local-startup documentation.

## Out of scope

- Database writes, schema changes and Alembic migrations.
- Executing a generated task, launching an AI worker, controller approval,
  publication, pushing, merging or deployment through the browser.
- Gemini credentials, API calls, billing activation or audio persistence.
- Removing or rewriting Streamlit.
- Authentication and non-loopback network access.

## Allowed changed-file scope

- `main.py`
- `requirements.txt`
- `advancore/api/**`
- `frontend/**`
- `tests/test_api_*.py`
- `docs/architecture/DECOUPLED_LOCAL_CONSOLE.md`
- `tasks/TASK-126-decoupled-api-frontend-scaffold.md`

## Database impact

None. Read endpoints may open a database session, but the API rolls the session
back and closes it without committing. No migrations or operational data writes
are authorised.

## Acceptance criteria

- [x] FastAPI imports and starts on `127.0.0.1:8000`.
- [x] The existing Streamlit entry point is unchanged.
- [x] System status exposes bounded health facts without secrets.
- [x] Projects and Knowledge are retrieved through existing repositories and
      services using rollback-only sessions.
- [x] Owner Goal submission returns a dry-run preview with no planner launch,
      task-file write, worker execution or publication.
- [x] The frontend provides truthful empty/error states and contains no sample
      operational or financial figures.
- [x] Voice capture is user-initiated, memory-only and cannot auto-submit.
- [x] CORS is limited to approved loopback origins.
- [x] Existing migrations and database schema are unchanged.
- [x] Focused and full test suites pass.
- [x] Completion report is produced before commit.

## Test requirements

- API startup and static-file response tests.
- Status, Projects and Knowledge response-contract tests using fakes.
- Owner Goal validation and dry-run boundary tests.
- CORS allowed/disallowed preflight tests.
- Disabled voice-WebSocket boundary test.
- Full existing pytest suite, `git diff --check`, and a migration-path diff.

## Constraints

- Bind only to `127.0.0.1` by default.
- Never expose credentials, environment values or database connection strings.
- Do not use CORS as a substitute for authentication or loopback binding.
- Do not place Gemini or other provider credentials in browser JavaScript.
- A final voice transcript must remain editable and require explicit submission.
- Keep provider integration replaceable and disabled in this scaffold.

## Owner decisions

None for this scaffold. Activating Gemini, introducing API billing, enabling
non-local access or adding any mutating endpoint requires a separate owner
decision and governed task.

## Completion report

### Implemented

- Added a thin FastAPI entry point and presentation-independent API package.
- Added bounded status, Projects, Knowledge and dry-run Owner Goal endpoints.
- Added a disabled-by-default WebSocket voice boundary.
- Added a responsive static Tailwind-assisted control console with local CSS
  animations and vanilla JavaScript.
- Kept colours, controls and animations in replaceable presentation files so
  later owner-selected themes do not affect business or governance logic.
- Added architecture documentation and contract tests.

### Files changed

- `main.py`
- `requirements.txt`
- `advancore/api/__init__.py`
- `advancore/api/app.py`
- `advancore/api/dependencies.py`
- `advancore/api/schemas.py`
- `advancore/api/routes/__init__.py`
- `advancore/api/routes/owner_goals.py`
- `advancore/api/routes/read_models.py`
- `advancore/api/routes/status.py`
- `advancore/api/routes/voice.py`
- `frontend/index.html`
- `frontend/styles.css`
- `frontend/app.js`
- `frontend/audio.js`
- `tests/test_api_console.py`
- `docs/architecture/DECOUPLED_LOCAL_CONSOLE.md`
- `tasks/TASK-126-decoupled-api-frontend-scaffold.md`

### Database changes

None.

### Tests and results

- Focused API suite: 7 passed.
- Full isolated suite: 1,260 passed and 2 skipped using an in-memory SQLite
  test URL; no live PostgreSQL connection was used.
- Local Uvicorn startup: passed on `127.0.0.1:8000`.
- Browser verification: page rendered, Owner Goal returned `dry_run` with no
  task write or worker launch, and voice WebSocket returned disabled without
  accepting audio.
- `git diff --check`: passed.
- Migration diff: empty.
- One upstream FastAPI/Starlette test-client deprecation warning remains; it
  does not affect runtime or test success.

### Assumptions

- The FastAPI console will run beside Streamlit during the transition.
- The first task-submission experience is a dry-run preview rather than a task
  artifact write.
- Python 3.10 or later is used, consistent with the existing AdvanCore
  environment and code syntax.

### Risks / unresolved issues

- Gemini Live transcription requires a separately approved provider adapter,
  credential flow and usage policy.
- Tailwind's browser CDN is suitable for this local scaffold but should be
  replaced by a locally built, pinned CSS asset before production deployment.
- The current FastAPI test client emits one upstream deprecation warning about
  the future HTTP client package transition.

### Decisions required

Owner review of this exact pre-commit diff.

### Recommended next step

Commit this verified scaffold on the TASK-126 feature branch if the owner
accepts the pre-commit review; do not merge to `main`.
