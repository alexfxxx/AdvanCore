# TASK-083 — Worker Usage and Health Dashboard

STATUS: REVIEW

## Objective

Provide truthful provider-neutral worker health summaries and show Kimi,
Codex, and Gemini status on the customizable dashboard without inventing usage
or probing accounts.

## Business context

The owner needs to see whether AI workers are usable before a long task starts.
Only Kimi currently has controller-owned usage evidence. Codex is checked at
launch, and Gemini is a setup-required candidate with no connected usage feed.

## In scope

- Add immutable provider-neutral health summaries backed by the registry.
- Map existing Kimi usage evidence to available, paused, stale, or unavailable.
- Represent Codex as approved with readiness checked at launch and no inferred
  quota.
- Represent Gemini as a setup-required candidate with no inferred subscription
  or API usage.
- Add Gemini to the allowlisted removable dashboard worker cards.
- Add focused service, preference, and dashboard tests.

## Out of scope

- Account/CLI probing, login, API keys, billing, Gemini activation, executable
  launch, new database settings, background refresh, or fabricated balances.

## Allowed changed-file scope

- `tasks/TASK-083-worker-health-dashboard.md`
- `advancore/services/worker_health_service.py`
- `advancore/services/dashboard_preference_service.py`
- `advancore/pages/dashboard.py`
- `tests/test_worker_health_service.py`
- `tests/test_dashboard_preference_service.py`
- `tests/test_dashboard_page.py`

## Database impact

None. Existing display preferences remain valid; no migration or automatic
preference rewrite occurs.

## Acceptance criteria

- [x] Kimi status uses only validated controller-owned usage evidence.
- [x] Stale/missing Kimi evidence is not shown as available.
- [x] Codex quota is not inferred from chat history or subscription.
- [x] Gemini is clearly setup-required and inactive.
- [x] Gemini can be added or removed through the existing allowlisted
      customization control.
- [x] Display choices grant no worker authority.
- [x] Focused tests and `git diff --check` pass.
- [x] Completion report produced.

## Constraints

- Do not read browser/account state or secret environment variables.
- Health display is advisory; `agent_runner` launch gates remain authoritative.
- Do not modify or merge to `main`.

## Owner decisions

None for truthful status display. Gemini setup remains deferred.

## Completion report

### Implemented

- Added frozen provider-neutral health summaries backed by the immutable worker
  registry and existing Kimi usage evidence.
- Mapped Kimi to available/paused/stale/unavailable without provider probing.
- Represented Codex as checked at launch with no inferred quota and Gemini as a
  setup-required inactive candidate with no connected usage.
- Added Gemini to the allowlisted removable worker-card catalogue and rendered
  clear non-authority wording on the dashboard.

### Files changed

- Task record, new worker health service, dashboard/preferences, and focused
  health, preference, and page tests.

### Database changes

None. Existing saved worker-card selections remain valid and unchanged.

### Tests and results

- Health, dashboard preference/page, and Kimi usage regression suite: 69 passed.
- `git diff --check`: passed.

### Assumptions

- Codex readiness remains a launch-time check because AdvanCore has no approved
  provider-quota feed for it.

### Risks / unresolved issues

- Gemini and Codex usage values remain unavailable until separately approved,
  authoritative provider evidence exists.

### Decisions required

None for the truthful display.

### Recommended next step

Proceed with TASK-084 safe multi-worker failover and resumable handoff state.
