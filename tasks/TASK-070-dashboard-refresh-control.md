# TASK-070 — Dashboard Refresh Control

STATUS: REVIEW

## Objective

Give the owner a clear manual control that reloads the dashboard's latest
available counts, worker-usage status, and saved layout without navigating away.

## Business context

The command center shows live database summaries and local usage state, but the
owner currently has no obvious way to request a fresh reading while staying on
the page. Streamlit reruns a page when a button is clicked, so an explicit
control can provide this usability improvement without background polling or a
new dependency.

## Facts

- Dashboard data is loaded during each Streamlit page run.
- Clicking a Streamlit button starts a new run before later dashboard data is
  loaded.
- Automatic polling frequency, provider calls, and mobile deployment are not
  approved in this task.

## In scope

- Add an obvious `Refresh dashboard` button near the dashboard heading.
- Confirm when the fresh page run has been requested.
- Reload the existing preferences, Kimi usage summary, and database overview
  through their existing bounded services.
- Add isolated page tests for the control and its message.

## Out of scope

- Background polling, timers, provider API calls, cache policy, database or
  schema changes, worker launches, authorization changes, or `main`.

## Allowed changed-file scope

- `tasks/TASK-070-dashboard-refresh-control.md`
- `advancore/pages/dashboard.py`
- `tests/test_dashboard_page.py`

## Database impact

None.

## Acceptance criteria

- [x] The dashboard shows a clearly labelled manual refresh control.
- [x] Activating it loads the page through the existing services and shows a
      bounded success confirmation.
- [x] No automatic loop, provider launch, or governance change is introduced.
- [x] Focused and full tests pass.
- [x] Completion report produced.

## Test requirements

- Verify the refresh control is rendered.
- Verify activation shows the safe refresh confirmation while normal summary
  rendering continues.
- Run focused dashboard-page tests, the full suite, and `git diff --check`.

## Constraints

- Keep the control dependency-free and compatible with the existing light UI.
- Do not claim that unavailable provider quota data became authoritative.
- Do not bypass any existing service or error boundary.

## Owner decisions

None. This is a bounded presentation control over the page's existing reload
behavior.

## Completion report

### Implemented

- Added a clearly labelled `Refresh dashboard` control under the command-center
  heading.
- Kept refresh behavior inside Streamlit's normal page rerun so the existing
  preference, usage, and database services load their latest available state.
- Added a bounded success confirmation and explanatory hover help.
- Added isolated coverage for control visibility, activation, confirmation,
  and continued summary rendering.

### Files changed

- `tasks/TASK-070-dashboard-refresh-control.md`
- `advancore/pages/dashboard.py`
- `tests/test_dashboard_page.py`

### Database changes

None.

### Tests and results

- Focused dashboard-page tests: 8 passed.
- Full repository suite: 927 passed in 171.79 seconds.
- `git diff --check`: passed.
- Live test-port verification confirmed the button is visible; clicking it
  showed the safe confirmation and retained the real total-project metric.

### Assumptions

- A Streamlit button click starts the fresh page run before later dashboard
  data is loaded, so no second forced rerun is required.

### Risks / unresolved issues

- This is owner-requested refresh, not automatic polling. External provider
  readings remain unavailable when their existing authoritative probe cannot
  supply them.

### Decisions required

None.

### Recommended next step

- Publish for independent GitHub verification and integrate only into
  `projects-lifecycle-recovery` when clean.
