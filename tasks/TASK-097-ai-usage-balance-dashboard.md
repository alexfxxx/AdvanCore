# TASK-097 — Truthful AI Usage Balance Dashboard

STATUS: REVIEW

## Objective

Show Kimi, Codex, and Gemini usage or balance evidence on the Dashboard without
inventing provider allowances, scraping accounts, or changing worker authority.

## Business context

The owner wants one simple place to understand whether each AI service has
capacity before starting work. Kimi has an existing controller-owned weekly
percentage contract. Gemini now has a successful Google Pro OAuth session and a
bounded smoke-run token observation, but its CLI does not expose a stable
machine-readable remaining percentage. Codex subscription balance also has no
approved machine-readable feed; OpenAI's organization Usage API applies to
separately billed API usage rather than the Codex desktop subscription.

## In scope

- Add a provider-neutral, read-only usage display model for Kimi, Codex, and
  Gemini.
- Reuse validated Kimi weekly evidence and its existing 20% automation policy.
- Add strict controller-owned observation receipts for bounded Codex/Gemini
  facts such as last-run tokens and an owner-verified provider percentage.
- Show provider balance, observed usage, evidence freshness, reset information,
  role, and routing status using plain language.
- Show `Unavailable` when no supported reading exists.
- Keep observations outside Git and every worker repository with owner-only
  permissions and no credentials, prompts, responses, or account identifiers.
- Add deterministic service, CLI-boundary, and Dashboard tests.

## Out of scope

Provider account scraping, browser/session reading, credentials, OAuth changes,
API keys, billing, credit purchase, fabricated quota conversion, background
polling, worker activation, routing changes, database changes, deployment, or
merge to `main`.

## Allowed changed-file scope

- `tasks/TASK-097-ai-usage-balance-dashboard.md`
- `advancore/services/ai_usage_dashboard_service.py`
- `advancore/pages/dashboard.py`
- `docs/runbooks/AI_USAGE_DASHBOARD.md`
- `tests/test_ai_usage_dashboard_service.py`
- `tests/test_dashboard_page.py`

## Database impact

None. Display observations are bounded local JSON receipts in controller-owned,
Git-ignored OS-account state.

## Acceptance criteria

- [x] Kimi uses only its validated controller-owned weekly evidence.
- [x] Codex and Gemini never show an inferred balance.
- [x] A measured request token count is labelled as an observation, not a quota.
- [x] Missing, stale, malformed, or unsafe evidence is visibly unavailable.
- [x] Gemini remains candidate-only and Codex remains the approved fallback.
- [x] Dashboard controls cannot alter worker authority or provider evidence.
- [x] Focused and full tests plus `git diff --check` pass.

## Owner decisions

Approved on 26 August 2026: show all safely available Kimi, Codex, and Gemini
usage balances on the Dashboard and proceed with this next governed step.

## Completion report

### Implemented

- Added a provider-neutral read-only usage summary for Kimi, Codex, and Gemini.
- Reused Kimi's validated controller evidence and 20% / 60-minute automation
  limits without changing launch policy.
- Added strict, owner-only local observation receipts for bounded Codex and
  Gemini facts.
- Recorded the successful Gemini smoke request as 31,142 observed tokens while
  leaving its exact Google Pro balance unavailable.
- Updated the Dashboard to distinguish current balance, observed request usage,
  stale evidence, and unavailable evidence in plain language.

### Files changed

- `advancore/services/ai_usage_dashboard_service.py`
- `advancore/pages/dashboard.py`
- `docs/runbooks/AI_USAGE_DASHBOARD.md`
- `tests/test_ai_usage_dashboard_service.py`
- `tests/test_dashboard_page.py`
- `tasks/TASK-097-ai-usage-balance-dashboard.md`

### Database and secrets

No database, migration, credential, OAuth, API key, billing, or routing change.
Provider observations remain outside Git and worker workspaces with owner-only
permissions and contain no prompt, response, transcript, or account identifier.

### Verification

- Focused tests: 52 passed.
- Full suite: 1,119 passed and 2 skipped using the approved loopback test
  database.
- Python compilation and `git diff --check`: passed.

### Assumptions and known limitations

- Kimi remains the only provider with a validated controller-owned weekly
  percentage feed.
- Google Pro and the Codex desktop subscription do not currently expose an
  approved machine-readable remaining balance to AdvanCore. Their cards fail
  closed to `Unavailable` rather than estimate.
- The Gemini token count is a historical request observation, not an allowance
  or billing reading.

### Review and next step

Implementation is ready for independent review on its feature branch. Do not
merge to `main`; any accepted PR must target `projects-lifecycle-recovery`.
