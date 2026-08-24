# TASK-067 — Customizable Command Center

STATUS: REVIEW

## Objective

Adapt the useful visual direction from the owner-provided Gemini dashboard into
the existing AdvanCore Streamlit application, using real AdvanCore data and a
safe, persistent add/remove experience for dashboard modules and visible AI
worker cards.

## Facts

- AdvanCore currently uses Streamlit and PostgreSQL, not FastAPI, Node.js,
  Tailwind, or a standalone browser application.
- The supplied prototype contains hard-coded transport/finance values that do
  not exist in the current AdvanCore schema.
- The governed unattended implementation route is Kimi-Swarm first with Codex
  as the approved fallback; `agent_runner` remains the authority boundary.
- The existing `system_settings` table can store the single-owner local
  dashboard preference without a schema change.

## Approved interpretation

“Add/remove functions” means show or hide registered dashboard modules and AI
worker cards. It does not register an executable, grant credentials, change the
worker route, or authorize an AI provider.

## In scope

- Add a responsive command-center theme using local CSS only.
- Rework the approved theme to a light, high-contrast business interface when
  the owner rejects the initial dark background.
- Use a cohesive set of locally stored CC0 SVG Repo navigation icons.
- Add restrained hover, focus, entrance, and edge-glow micro-interactions with
  reduced-motion support.
- Replace fake revenue, route, vehicle, driver, and customer values with the
  existing Platform, AI workforce, Projects, Knowledge, and Activity modules.
- Let the owner show/hide approved modules and the Kimi-Swarm/Codex worker cards.
- Save one bounded, allowlisted preference in PostgreSQL so it survives browser
  refreshes and can follow the same single-owner app between devices.
- Fail safely to the default layout when stored preference data is absent or
  invalid.
- Clearly state that display choices do not change worker authorization.
- Add repository, service, page, and theme tests.

## Out of scope

- Fake or inferred financial/transport data.
- Drag-and-drop JavaScript, external CDN scripts, browser local storage, or a
  second FastAPI/Node server.
- Arbitrary executable/provider registration, credentials, worker routing,
  controller authority, task approvals, usage-limit invention, or automatic AI
  launches.
- Multi-user identity, per-user permissions, public/mobile deployment, schema
  changes, production data deletion, or `main`.

## Allowed changed-file scope

- `tasks/TASK-067-customizable-command-center.md`
- `app.py`
- `advancore/ui/__init__.py`
- `advancore/ui/theme.py`
- `advancore/assets/icons/*.svg`
- `advancore/assets/icons/README.md`
- `advancore/repositories/__init__.py`
- `advancore/repositories/setting.py`
- `advancore/services/dashboard_preference_service.py`
- `advancore/pages/dashboard.py`
- `tests/test_theme.py`
- `tests/test_repositories.py`
- `tests/test_dashboard_preference_service.py`
- `tests/test_dashboard_page.py`

## Owner decisions

The owner supplied the Gemini design and authorized adaptation for AdvanCore,
including add/remove functions, on 24 August 2026.

The owner then rejected the dark background, requested readable sidebar text,
specified SVG Repo icons, supplied animation/login interaction references, and
approved merge into `projects-lifecycle-recovery` after rework on
24 August 2026.

## Assumptions

- AdvanCore remains a single-owner local application for this slice, so one
  saved dashboard preference is appropriate until authentication exists.
- Kimi-Swarm and Codex are the only worker cards needed in the default command
  center because they are the fixed unattended primary/fallback route.

## Acceptance criteria

1. No hard-coded business KPI is presented as live data.
2. The owner can remove and re-add every dashboard module.
3. The owner can remove and re-add Kimi-Swarm and Codex cards without changing
   execution authority.
4. Saved choices reload from PostgreSQL and invalid values fail to defaults.
5. The layout remains usable at phone and laptop widths.
6. No external scripts, credentials, or raw provider usage are introduced.
7. Focused and full test suites pass.

## Completion report

### Implemented

- Reworked the initial design into a light, high-contrast command-center theme
  with readable sidebar labels and responsive laptop, tablet, and phone rules.
- Added six cohesive, locally served CC0 SVG Repo navigation icons and recorded
  their source pages.
- Added restrained entrance, hover, focus, lift, and edge-glow motion with a
  reduced-motion fallback.
- Replaced the prototype's fake business figures with existing Platform, AI
  workforce, Projects, Knowledge, and Activity data.
- Added allowlisted show/hide controls for every dashboard module and for the
  Kimi-Swarm/Codex worker cards.
- Persisted the single-owner layout in the existing `system_settings` table.
- Added strict JSON/version/catalogue validation and safe default recovery.
- Kept AI display preferences separate from `agent_runner` execution authority.

### Files changed

- `tasks/TASK-067-customizable-command-center.md`
- `app.py`
- `advancore/ui/__init__.py`
- `advancore/ui/theme.py`
- `advancore/assets/icons/*.svg`
- `advancore/assets/icons/README.md`
- `advancore/repositories/__init__.py`
- `advancore/repositories/setting.py`
- `advancore/services/dashboard_preference_service.py`
- `advancore/pages/dashboard.py`
- `tests/test_theme.py`
- `tests/test_repositories.py`
- `tests/test_dashboard_preference_service.py`
- `tests/test_dashboard_page.py`

### Database changes

- No schema or migration change.
- The existing `system_settings` table stores one bounded
  `dashboard.command_center.v1` preference. Live verification restored the
  complete default value after testing removal and persistence.

### Tests executed and results

- Initial focused preference/page/theme/repository tests: 38 passed.
- Full repository suite after the light-theme rework: 926 passed.
- Final validation-boundary focused tests passed after hardening non-string
  input handling.
- `git diff --check`: passed.
- Live remove/save/reload proved Knowledge and Kimi cards stayed hidden.
- Live restore proved all five modules and both worker cards returned.
- Phone-width visual inspection proved metric cards stack vertically.
- Live light-theme inspection proved the white sidebar, readable navigation,
  active-state highlight, and SVG icons render correctly.
- The supplied Facebook references were inspected as a CSS rendering sequence,
  a glowing-button treatment, and an animated login form; only restrained,
  accessible motion appropriate to the existing authenticated state was used.

### Assumptions

- The current local app remains single-owner; multi-user preferences wait for
  an authentication/identity design.
- User-added functions are drawn from the governed catalogue. Adding a new AI
  provider still requires a separately reviewed adapter and policy task.

### Risks / unresolved issues

- Android access still requires a separately approved hosting/network and
  authentication design; responsiveness alone does not expose the loopback app.
- A visual login screen was not added because AdvanCore has no authentication
  backend yet; presenting one would falsely imply an access-control boundary.
- Streamlit does not provide the prototype's drag-and-drop grid without a custom
  component; this task intentionally uses safer add/remove controls.
- Codex quota cannot be read authoritatively inside AdvanCore, so the UI labels
  it unavailable rather than estimating from chat history.

### Decisions required

- None if the updated independent checks pass. The owner explicitly approved
  merge into `projects-lifecycle-recovery`, not `main`, after this rework.

### Recommended next step

- Update PR #8 and rerun GitHub verification. If clean, integrate into
  `projects-lifecycle-recovery`, then decide whether TASK-068 should address
  real authentication/mobile hosting or additional business modules.
