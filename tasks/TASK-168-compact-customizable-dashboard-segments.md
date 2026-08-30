# TASK-168 — Compact Customizable Dashboard Segments

STATUS: COMPLETE

## Objective

Replace the decoupled console's single long document with a compact,
responsive workspace of approved dashboard segments that can be shown, hidden,
reordered and resized without changing operational data or governance.

## Business context

The owner cannot see enough of AdvanCore at one glance because the current
console renders every major section and all 27 Fleet records vertically. The
owner also reports that Chrome does not always match the intended CSS and
animation preview. The workspace must provide a useful high-level overview,
allow personal arrangement, and open detailed information only when requested.

## Facts

- The custom decoupled console is served at `http://127.0.0.1:8000`.
- The light Streamlit transition app is a separate interface at
  `http://127.0.0.1:8501`; it is not expected to match the custom console.
- The current decoupled console already uses a 12-column CSS grid, safe fixed
  themes, a full/reduced-motion preference and validated browser-local Fleet
  field preferences.
- Current CSS contains panel, pulse, ambient, breathing and orbit animations.
- Animations are intentionally reduced when the browser/operating system sends
  `prefers-reduced-motion: reduce` or when the browser-local Motion setting is
  `Reduced`.
- The current console renders Owner Goal, Voice, Readiness, Projects,
  Knowledge, Fleet, Dispatch, Fuel, Display and governance information in one
  document.
- The Fleet panel renders all 27 vehicle detail cards, which is the largest
  source of vertical length.
- Chrome cannot be inspected from the current controller session until its
  ChatGPT browser extension is connected. Therefore the exact Chrome-side
  cause is not yet proven.

## Recommended workspace design

### Default desktop grid

- Top left/centre, eight columns: Controller and live governed progress.
- Top right, four columns: Local readiness and worker/controller state.
- Middle left/centre, eight columns: compact Fleet overview.
- Middle right, four columns: Dispatch summary and exceptions.
- Lower row, four columns each: Fuel benchmark, Projects and Knowledge.
- Voice, display settings and governance explanations remain available from a
  utility drawer rather than occupying permanent full-width rows.

The default is an overview, not a commitment to render every detail at once.

### Segment behavior

- Add an explicit `Edit layout` mode.
- Allow drag ordering on desktop.
- Provide equivalent keyboard and touch move controls.
- Offer approved width choices such as Small, Medium, Wide and Full width.
- Allow approved segments to be shown or hidden.
- Allow a visible segment to be replaced from a code-owned segment catalogue.
- Prevent duplicate segment identifiers unless a segment explicitly supports
  multiple instances.
- Provide `Reset workspace` to restore the approved default.
- Store only validated segment identifiers, order, visibility and size in a
  versioned browser-local preference key.
- Do not allow arbitrary HTML, JavaScript, URLs, SQL, API calls or user-created
  schema fields as segments.

### Compact data behavior

- Fleet overview shows totals and a short, searchable/filterable vehicle list,
  not all 27 complete detail cards.
- Selecting a vehicle opens its full information in an accessible side drawer
  or modal without leaving the workspace.
- Project and Knowledge segments show bounded recent/active summaries with an
  explicit `View all` action.
- Dispatch shows today's headline counts and only actionable exceptions.
- Fuel shows the current recorded summary and dated market benchmark without
  expanding every source record by default.
- Detailed module pages remain available for deeper work.
- Segment data must remain truthful: no sample, invented or estimated business
  values.

### Browser consistency and motion

- Display the console build/version identifier in the UI so stale pages can be
  identified.
- Version static CSS and JavaScript asset URLs or apply bounded local-development
  cache headers so Chrome receives the current files after a rebuild.
- Keep a visible Motion selector with `Full` and `Reduced` choices.
- Show when Chrome/OS accessibility settings override full motion.
- Preserve `prefers-reduced-motion` support; do not force animation against an
  accessibility preference.
- Use animation only for short panel entry, state changes and subtle status
  indicators. Avoid movement that obscures operational information.
- Add a safe `Reset display and layout` action that removes only AdvanCore's
  allow-listed browser-local preference keys.

### Responsive behavior

- Desktop and tablet use the 12-column segment grid.
- Narrow mobile screens use a compact module switcher and one active segment at
  a time rather than a very long stacked page.
- Touch users receive explicit move and size controls; drag is never the only
  interaction.
- Layout preferences may differ by desktop/tablet/mobile breakpoint while
  sharing the same validated segment catalogue.

## In scope

- Create the approved segment catalogue and default placements.
- Convert the long decoupled console into the compact responsive workspace.
- Add safe layout edit, show/hide, reorder, replace, resize and reset controls.
- Add a compact Fleet overview and selected-vehicle detail drawer/modal.
- Bound Projects, Knowledge, Dispatch and Fuel summaries.
- Persist validated layout preferences in browser `localStorage` only.
- Add build/version and motion-state indicators.
- Prevent stale local CSS/JavaScript after approved rebuilds.
- Preserve existing controller-mediated Owner Goal and live progress behavior.
- Add unit/contract, accessibility, responsive and real-browser visual tests.

## Out of scope

- PostgreSQL models, data, migrations or connection configuration.
- Server-stored or cross-device layout synchronization.
- Arbitrary third-party widgets, custom scripts, iframe URLs or plugins.
- Changing approval, controller, worker, publication or database authority.
- Authentication, deployment, billing or `main`.
- Replacing the governed Streamlit edit surfaces in this task.
- Entering, importing or modifying real operational or finance data.

## Database impact

None. Dashboard arrangement remains a presentation preference in the current
browser and must never mutate PostgreSQL.

## Allowed changed-file scope

- `tasks/TASK-168-compact-customizable-dashboard-segments.md`
- `frontend/index.html`
- `frontend/styles.css`
- `frontend/app.js`
- `advancore/api/app.py` only if bounded local static-asset versioning or cache
  headers require it
- focused frontend/API contract and accessibility tests
- a non-secret visual-test evidence artifact if the repository's existing
  evidence policy allows it

## Acceptance criteria

- [x] The initial desktop view presents the recommended overview grid without
      rendering every full Fleet record.
- [x] Every approved segment can be moved using desktop drag and equivalent
      keyboard/touch controls.
- [x] Segments can be safely shown, hidden, resized and replaced only from the
      approved catalogue.
- [x] Invalid, duplicated, oversized, obsolete or unknown stored layout values
      fail closed to the approved default.
- [x] Layout changes persist after refresh and reset cleanly.
- [x] Fleet initially shows a bounded overview and opens one selected vehicle's
      full details on demand.
- [x] No layout action triggers a database write or controller action.
- [x] Desktop, tablet and mobile layouts avoid an unnecessarily long all-module
      document.
- [x] Chrome can identify the current build and does not retain stale CSS/JS
      after an approved local rebuild.
- [x] The UI truthfully reports when reduced motion is caused by the saved
      preference or browser/OS accessibility settings.
- [x] Controller and `agent_runner` governance remain unchanged.
- [x] Focused tests, full isolated regression, browser checks and Bugbot pass.
- [x] Completion report is produced before publication.

## Test requirements

- Test segment-catalogue allowlisting, deduplication, supported sizes and safe
  defaults.
- Test drag, keyboard and touch-equivalent ordering in both directions and to
  first/final positions.
- Test show/hide, replace, resize, persistence, version migration and reset.
- Test malformed and hostile `localStorage` content without evaluating it.
- Test that layout actions make no write API calls.
- Test compact Fleet limits and selected-detail opening against synthetic data.
- Test build/version indicators and static-asset cache/version behavior.
- Test saved reduced motion and `prefers-reduced-motion` reporting.
- Visually check normal desktop, narrow desktop/tablet and Android-sized mobile
  viewports.
- Check Chrome after connecting the ChatGPT browser extension or complete a
  documented owner-observed Chrome verification.
- Run `git diff --check`, focused tests, full isolated regression and Bugbot.

## Constraints

- `agent_runner` remains the authority boundary.
- The frontend may submit an Owner Goal only through the existing controller
  workflow.
- No segment may launch a worker, approve work, mutate data, commit, push,
  merge or deploy directly.
- Browser-local preferences must contain presentation identifiers only—never
  credentials, prompts, operational records or personal data.
- Accessibility motion preferences must remain respected.
- Kimi/Gemini/Codex routing and credentials are not part of this task.
- Publication may target a feature branch and later
  `projects-lifecycle-recovery`, never `main`.

## Owner decisions

- APPROVED: recommended default desktop grid.
- APPROVED: selected-vehicle side drawer replaces simultaneous rendering of all
  27 full Fleet detail cards.
- APPROVED: browser-local layout persistence for this phase; cross-device
  synchronization remains deferred until authentication is designed.

## Completion report

### Implemented

- Replaced the long all-module document with a validated 12-column segment
  workspace and compact approved default arrangement.
- Added browser-local show/hide, size, replace, drag, keyboard/touch move and
  reset controls backed by a versioned allowlisted preference format.
- Added a one-segment mobile switcher and responsive tablet/mobile layouts.
- Replaced 27 simultaneous Fleet detail cards with truthful totals, bounded
  search results and an accessible selected-vehicle side drawer.
- Bounded Projects, Knowledge and Dispatch summaries and prioritised active,
  recent lifecycle records.
- Added build and motion-state labels plus versioned static asset URLs and a
  no-store policy for the local index.
- Repaired all Bugbot findings, including Fleet error/drawer freshness,
  truthful storage-failure reporting and Knowledge `superseded` ordering.

### Files changed

- `advancore/api/app.py`
- `frontend/index.html`
- `frontend/styles.css`
- `frontend/app.js`
- `tests/test_api_console.py`
- `tests/test_frontend_fleet_contract.py`
- `tests/test_frontend_workspace_contract.py`
- `tasks/TASK-168-compact-customizable-dashboard-segments.md`

### Database changes

None. No model, migration, schema or operational-data write was made.

### Tests and results

- JavaScript syntax and `git diff --check`: passed.
- Focused frontend/API suite: 19 passed.
- Full isolated SQLite regression after final repair: 1,581 passed, 2 skipped.
- Live read-only visual check: desktop grid, 27-vehicle compact Fleet overview,
  selected-vehicle drawer, layout persistence/reset and Android-sized
  one-segment switching passed with no browser console errors.
- Final Bugbot review: CLEAN.

### Assumptions

- The decoupled console on port 8000 remains the primary overview while
  Streamlit remains a temporary governed edit surface.
- A fixed safe segment catalogue is acceptable; arbitrary user-authored widgets
  remain out of scope.

### Risks / unresolved issues

- Browser-local choices do not synchronize across devices; that remains
  intentionally deferred until authentication design.
- The running port-8000 Docker/local service must be rebuilt or restarted after
  merge before the owner sees this build in the existing browser tab.

### Decisions required

None for TASK-168.

### Recommended next step

Publish the clean feature branch through a PR into
`projects-lifecycle-recovery`, never `main`, then rebuild the local app under a
separate activation step.
