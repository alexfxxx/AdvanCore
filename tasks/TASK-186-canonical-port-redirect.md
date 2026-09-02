# TASK-186 — Canonical Port Redirect

## Status

READY FOR REVIEW

## Objective

Make the custom FastAPI HTML/CSS/JavaScript console the unmistakable local
AdvanCore entry point even when an owner opens the historical port 8501.
Streamlit remains available temporarily on port 8502 for workflows that have
not yet transferred.

## Confirmed decisions

- `http://127.0.0.1:8000` remains the primary AdvanCore application.
- `http://127.0.0.1:8501` redirects browser navigation to the primary app.
- Streamlit moves from port 8501 to `http://127.0.0.1:8502`.
- Every process remains bound to loopback only.
- The redirect is temporary and non-cacheable so the local mapping remains
  reversible.
- TASK-187 and all Claude installation, authentication, configuration and
  worker-routing work are deferred by the owner.

## Approved scope

- Add one standard-library loopback redirect process.
- Launch, monitor and stop the primary app, redirect and Streamlit together.
- Extend local readiness checks to verify all three endpoints and the exact
  redirect destination.
- Update primary-console links and current owner/runbook documentation.
- Add focused tests for redirect safety, startup wiring and health checks.

## File allowlist

- `scripts/redirect-legacy-interface.py`
- `scripts/start-advancore.sh`
- `scripts/check-local-interfaces.py`
- `frontend/index.html`
- `README.md`
- `CURRENT_STATE.md`
- `docs/architecture/DECOUPLED_LOCAL_CONSOLE.md`
- `docs/architecture/PRIMARY_CONSOLE_CUTOVER.md`
- `docs/runbooks/CORE_LOCAL_OPERATIONS.md`
- `docs/runbooks/LOCAL_STARTUP.md`
- `tests/test_legacy_interface_redirect.py`
- `tests/test_local_interface_health.py`
- `tests/test_local_startup_script.py`
- `tests/test_primary_console_cutover.py`
- `tasks/TASK-186-canonical-port-redirect.md`

## Explicitly out of scope

- PostgreSQL, models, repositories, business services or Alembic migrations.
- Real operational data or backups.
- Controller, `agent_runner` or AI-worker behaviour.
- Claude Code or TASK-187 implementation.
- Deployment, credentials, billing, publication to `main`, or removal of
  Streamlit.

## Acceptance criteria

- Port 8000 serves the existing primary CSS application unchanged.
- A GET or HEAD request to loopback port 8501 returns a non-cacheable redirect
  to exactly `http://127.0.0.1:8000/`.
- The redirect does not reflect arbitrary paths or query strings and does not
  accept a caller-controlled target.
- Streamlit starts on loopback port 8502.
- The launcher treats any of the three local interface processes stopping as a
  failed paired startup and safely closes the survivors.
- Readiness reports healthy only when the API, exact redirect and Streamlit
  health endpoint all respond as expected.
- Focused and full regression tests pass without a live database or external
  network.

## Implementation plan

1. Add the bounded standard-library redirect server and focused tests.
2. Update launcher lifecycle handling and fixed-port health checks.
3. Update current UI links and operational documentation.
4. Run focused checks, the full regression suite and a scoped diff review.
5. Commit and prepare a PR into `projects-lifecycle-recovery`, not `main`.

## Database changes

None.

## Owner decisions required

None for implementation. A later merge remains a separate governed action.

## Completion report

### Implemented

- Added a standard-library HTTP server bound only to `127.0.0.1:8501` that
  redirects GET and HEAD navigation to exactly `http://127.0.0.1:8000/`.
- Made the redirect non-cacheable and prevented request paths, query strings or
  caller input from changing its destination.
- Moved temporary Streamlit startup and primary-console links to loopback port
  8502.
- Extended paired startup, shutdown and readiness handling to cover the
  primary app, compatibility redirect and temporary Streamlit interface.
- Updated current architecture and owner-operation documentation.

### Files changed

Only the file allowlist above.

### Database changes

None. No migration or operational-data action was performed.

### Tests executed and results

- Shell syntax and Python compilation checks: passed.
- Focused redirect/startup/health/cutover tests: 15 passed.
- Full isolated SQLite regression: 1,639 passed, 2 skipped, 1 upstream
  deprecation warning.
- `git diff --check`: passed.

### Assumptions

- Existing local bookmarks may continue opening port 8501, so a reversible 307
  redirect is preferable to a browser-cacheable permanent redirect.
- Streamlit must remain available until its remaining governed workflows have
  transferred and the owner separately approves retirement.

### Risks / unresolved issues

- The currently running integrated app will retain the old port assignment
  until this change is reviewed, merged into `projects-lifecycle-recovery` and
  the local launcher is restarted.

### Decisions required

- Review and merge of the resulting PR into `projects-lifecycle-recovery`, not
  `main`.

### Recommended next step

After clean PR review and owner-approved merge, restart the local app and verify
that 8000 serves the CSS console, 8501 redirects to it and 8502 serves the
temporary Streamlit interface.
