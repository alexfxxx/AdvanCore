# TASK-078 — Dashboard Visual and Voice Foundation

STATUS: REVIEW

## Objective

Add a restrained futuristic visual layer to the existing light Streamlit
command center, including a reusable dark neon Plotly fuel-trend panel, one
local static Streamlit custom component, and an explicit microphone-based
confirmation step for bounded fuel-view filters.

## Business context

The owner wants a more interactive “Jarvis” feel without losing the readable
light business interface already approved in TASK-067. Fuel records do not yet
exist in the AdvanCore operational schema, so the visual foundation must be
ready for real data without presenting invented figures as business facts.

## Facts

- The application is a local Streamlit app with a light, responsive command
  center and PostgreSQL as its operational database.
- The owner-provided design example includes hard-coded transport and financial
  values that are not present in AdvanCore.
- Streamlit `st.audio_input` records microphone audio but does not transcribe or
  understand commands by itself.
- TASK-077 is reserved for Local Backup and Recovery Foundation and is approved
  to run after this visual layer.
- UniFace and facial authentication are no longer planned at the owner's
  direction.

## Approved interpretation

- Preserve the light application shell. Dark styling is limited to the fuel
  chart and voice-command panel.
- “Voice confirmation” means the owner first chooses one allowlisted fuel-view
  filter, records a short confirmation, and then presses an explicit confirm
  button. Audio is not transcribed, uploaded to an AI service, saved to disk, or
  treated as identity evidence.
- A recorded voice signal alone never changes a filter and never grants agent
  authority.
- Until real fuel records are introduced by a separate governed task, the live
  chart shows a clear no-data state rather than synthetic business numbers.

## In scope

- Add Plotly as the chart dependency and require a Streamlit version that
  provides the stable `st.audio_input` API.
- Add a reusable dark, transparent, neon fuel line-chart builder that accepts
  typed real data points and renders an honest empty state when none exist.
- Add one static local Streamlit v2 custom component for fuel-system status,
  with no remote scripts, fonts, trackers, or user-supplied HTML.
- Add bounded 7-, 30-, and all-reading fuel-view choices.
- Add microphone capture and explicit confirmation for applying the selected
  fuel-view choice in the current session.
- Keep keyboard/button-only filter application available for accessibility.
- Add focused component, chart, dashboard interaction, dependency, and safety
  tests.

## Out of scope

- Fuel database tables, sample or invented operational records, imports,
  accounting rules, efficiency targets, forecasts, or alerts.
- Speech-to-text, natural-language command parsing, wake-word listening,
  background microphone access, audio persistence, biometric identity, voice
  authentication, UniFace, or any external AI/audio service.
- A global dark theme, remote JavaScript/CDN assets, arbitrary HTML input,
  executable dashboard plugins, changes to `agent_runner`, worker authority,
  credentials, deployment, login, or `main`.

## Allowed changed-file scope

- `tasks/TASK-078-dashboard-visual-voice-foundation.md`
- `requirements.txt`
- `advancore/pages/dashboard.py`
- `advancore/ui/custom_components.py`
- `advancore/ui/fuel_trends.py`
- `advancore/ui/theme.py`
- `tests/test_dashboard_page.py`
- `tests/test_dashboard_visual_foundation.py`
- `tests/test_theme.py`

## Database impact

None. This task does not create or alter operational fuel data.

## Acceptance criteria

- [x] The existing light shell remains readable and responsive.
- [x] The fuel panel uses a dark transparent Plotly layout with neon line
      styling when supplied real points.
- [x] The live app never presents the attachment's sample figures as facts.
- [x] No-data fuel state is explicit and does not fabricate a trend.
- [x] The custom component is local, static, reduced-motion aware, and has no
      remote dependency.
- [x] Only allowlisted fuel windows can be selected.
- [x] Recording audio alone never applies a filter.
- [x] Voice-confirm and manual-apply controls both require an explicit click.
- [x] Audio is not transcribed, saved, logged, or sent to a provider.
- [x] Focused and full tests pass.
- [x] Completion report produced.

## Test requirements

- Test populated and empty Plotly figure construction and bounded windowing.
- Test static component safety, responsiveness, and reduced-motion support.
- Test no-audio, recorded-but-unconfirmed, voice-confirmed, and manual filter
  paths.
- Run focused tests, full repository tests, compilation, and `git diff --check`.

## Constraints

- Keep dynamic values out of unsafe HTML.
- Do not use microphone content as approval, authentication, or controller
  evidence.
- Do not add a transcription dependency or network call under this task.
- Preserve `agent_runner` as the execution authority boundary.
- Preserve GitHub as source of truth and PostgreSQL as the operational database.
- Do not modify or merge to `main`.

## Owner decisions

The owner requested Streamlit custom components, a dark neon fuel-trend chart,
and an audio-input confirmation trigger on 25 August 2026. The same direction
explicitly removed UniFace from the roadmap and approved TASK-077 Local Backup
and Recovery Foundation after the visual layer.

## Completion report

### Implemented

- Added a modern Streamlit v2 local status component with isolated styling,
  neon edge motion, and reduced-motion support.
- Added a typed Plotly fuel-trend builder with bounded 7-, 30-, and all-reading
  windows, dark translucent styling, layered cyan glow for real readings, and
  an axis-free no-data state.
- Added the live dashboard fuel console without copying any invented figures
  from the supplied prototype.
- Added microphone capture as an explicit confirmation signal for a selected
  allowlisted view; recording alone performs no action and a manual accessible
  path remains available.
- Corrected current Streamlit button-label contrast after live visual testing.
- Raised the Streamlit floor to the installed modern component API and added
  bounded Plotly 6 support.

### Files changed

- Task record and dependency requirements.
- Dashboard page and command-center theme.
- New local custom-component and fuel-trend modules.
- Focused dashboard, visual, component, dependency, and theme tests.

### Database changes

None.

### Tests and results

- Focused TASK-078, dashboard, and theme suite: 23 passed.
- Full repository suite: 987 passed, 2 intentionally skipped in 182.01 seconds.
- Compilation with an isolated bytecode cache: passed.
- `git diff --check`: passed.
- Live laptop inspection: v2 component, microphone state, controls, no-data
  message, button contrast, and axis-free Plotly panel rendered correctly.
- Live 390 × 844 phone inspection: no horizontal overflow and all visible text
  remained readable.

### Assumptions

- A fixed filter plus recorded confirmation is the safest useful local voice
  foundation until the owner separately approves a transcription engine.

### Risks / unresolved issues

- No real fuel trend can appear until a governed fuel data model and source are
  approved and implemented.
- This foundation deliberately does not interpret spoken words. A future local
  speech-to-text engine would require a separate privacy, resource, and command
  grammar decision.

### Decisions required

None for this approved scope.

### Recommended next step

Publish this feature branch for independent GitHub checks, integrate it into
`projects-lifecycle-recovery` when green, then implement the already approved
TASK-077 Local Backup and Recovery Foundation.
