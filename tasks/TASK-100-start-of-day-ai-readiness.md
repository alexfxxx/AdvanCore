# TASK-100 — Start-of-Day AI Authentication Readiness

STATUS: REVIEW

## Objective

At the beginning of each local app session, perform bounded non-generative
authentication checks for Kimi, Gemini, and Codex, refresh safe dashboard
evidence, and clearly ask the owner to log in before daily planning when a
credential is expired or unavailable.

## In scope

- Fixed, non-generative local CLI checks: Kimi provider configuration, Gemini
  model listing, and `codex login status`.
- One check per Streamlit session, with a manual Refresh button.
- Plain-language authenticated/login-required/unavailable status and exact
  owner-run login guidance; never collect credentials in AdvanCore.
- Update bounded dashboard facts without displaying raw CLI output.
- Mark authentication failure in worker reports as owner login required while
  still allowing the next approved worker to continue.
- Deterministic tests with mocked subprocesses; no live AI request in tests.

## Out of scope

Automated login, browser control, password/token storage, API keys, billing,
generative smoke prompts at every launch, account scraping, database changes,
deployment, or merge to `main`.

## Allowed changed-file scope

- `tasks/TASK-100-start-of-day-ai-readiness.md`
- `advancore/services/worker_auth_readiness_service.py`
- `advancore/pages/dashboard.py`
- `advancore/agent_runner/auto_pipeline.py`
- `docs/runbooks/WORKER_ROUTING.md`
- `tests/test_worker_auth_readiness_service.py`
- `tests/test_dashboard_page.py`
- `tests/test_worker_fallback.py`

## Database impact

None.

## Acceptance criteria

- [x] Each app session checks all three providers once without a model request.
- [x] Manual refresh reruns the bounded checks.
- [x] Raw output, credentials, tokens, account identifiers, and paths are hidden.
- [x] Login-required status presents safe provider-specific owner instructions.
- [x] Authentication failure reports request login and may continue to the next
      approved worker without weakening other stop conditions.
- [x] Dashboard usage/balance truth remains separate from authentication truth.
- [x] Focused and full tests plus `git diff --check` pass.

## Owner decisions

Approved on 26 August 2026: check AI authentication when the app launches,
refresh safe dashboard facts, ask the owner to log in first when credentials
expire, and then begin daily planning. Do not run a generative prompt merely to
check authentication.

## Completion report

### Implemented

- Added fixed non-generative authentication checks for Kimi provider
  configuration, Gemini model listing, and Codex login status.
- Added one check per Dashboard session plus explicit Refresh behavior.
- Added plain login-required instructions without collecting or displaying
  credentials or raw provider output.
- Added owner-login-required messages to authentication failover while retaining
  safe continuation to the next approved worker.

### Database and credentials

No database, migration, credential, OAuth, billing, model prompt, deployment,
or `main` change. AdvanCore never receives login secrets.

### Verification

- Focused tests: 37 passed.
- Full suite: 1,125 passed and 2 skipped.
- Python compilation and `git diff --check`: passed.
- No external AI model request was made by implementation or tests.

### Assumptions and risks

- Installed CLI status/list commands remain non-generative and preserve their
  current exit-code behavior.
- A provider CLI may be locally unavailable even when its account is healthy;
  the Dashboard reports that uncertainty rather than inventing authentication.
- The startup check does not replace launch-time authentication classification.

### Decisions required and next step

No additional policy decision is required. Independently review the stacked PR,
then merge TASK-097 through TASK-100 in dependency order into
`projects-lifecycle-recovery`, never directly into `main`.
