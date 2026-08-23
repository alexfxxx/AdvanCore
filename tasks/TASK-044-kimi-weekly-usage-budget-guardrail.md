# TASK-044 — Kimi weekly usage budget guardrail

STATUS: APPROVED

## Objective

Add a fail-closed, locally visible Kimi usage guardrail so AdvanCore does not launch Kimi after 20% of the provider's weekly allowance is reported used, limits Kimi automation runtime to one hour per week, and shows the current safe usage state on the Dashboard.

## Business context

The owner wants AdvanCore development automation to preserve provider capacity for urgent work. Current Kimi usage is already above the new weekly policy, so future Kimi launches must pause until a fresh post-reset reading is available. The owner should be able to see the state in the running app without reading terminal output.

## Facts

- The owner set a Kimi policy limit of 20% of the provider-reported weekly allowance.
- The owner set an additional local Kimi automation runtime limit of one hour per week.
- Kimi's current provider-reported weekly usage is 44%, with a reset expected on 28 August 2026.
- The installed Kimi CLI exposes the usage reading interactively rather than through a stable machine-readable API.
- `agent_runner` remains the authority boundary and already supports explicitly approved worker fallback.
- `.agent_runner/` is local and Git-ignored.

## In scope

- Add a provider-neutral local usage snapshot contract under `.agent_runner/usage/` with strict validation and no credentials.
- Add a Kimi policy of 20% provider-reported weekly usage and 3,600 seconds local runtime per provider week.
- Require a fresh, unexpired usage snapshot before every Kimi or Kimi-Swarm implementation/planner launch; stale, missing, malformed, reset-expired, at-limit, or runtime-exhausted state must block before process launch.
- Bound a Kimi launch timeout to the remaining weekly runtime and record actual elapsed Kimi process time in a separate local runtime ledger.
- Return a quota/capacity-classifiable failure so an already configured approved fallback may be considered through the existing integrity checks.
- Show Kimi reported usage, policy cap, runtime, reset, freshness and allowed/paused state on the Dashboard.
- Provide a small local snapshot-recording command in the usage service module for an approved controller/operator to refresh the provider reading.
- Document which capability is permanent AdvanCore policy and which local controller action refreshes the authenticated provider reading.
- Add deterministic service, worker and Dashboard tests.

## Explicitly out of scope

- Scraping Kimi websites, storing Kimi credentials, automating Kimi login, or claiming a stable Kimi quota API exists.
- Automatically purchasing credits, changing membership, bypassing provider limits, or inferring exact remaining tokens from local session logs.
- Changing Codex limits, owner/controller authority, fallback eligibility, repair/rework budgets, publication policy, or GitHub/main/deployment behavior.
- Allowing a worker to approve, refresh, or lower its own usage evidence during a run.
- Database, migration, model, repository, production-data, authentication, deployment, or dependency changes.

## Allowed changed-file scope

- `tasks/TASK-044-kimi-weekly-usage-budget-guardrail.md`
- `advancore/services/worker_usage_service.py`
- `advancore/agent_runner/worker.py`
- `advancore/pages/dashboard.py`
- `tests/test_worker_usage_service.py`
- `tests/test_worker_usage_guardrail.py`
- `tests/test_dashboard_page.py`
- `docs/runbooks/WORKER_USAGE_BUDGET.md`

## Database impact

None. Usage status and runtime accounting are local, bounded, Git-ignored JSON artifacts.

## Safety requirements

- Never store credentials, tokens, provider responses, browser contents, prompts, transcripts, environment dumps, or customer data.
- Treat malformed, missing, stale or expired evidence as unavailable and pause Kimi.
- Validate provider, percentages, timestamps, source labels, schema version and canonical artifact location.
- Use atomic local writes and reject ambiguous runtime ledgers.
- Check usage before process launch; a blocked launch must not run Kimi or mutate the repository.
- A usage block may enable only the existing explicit one-hop approved fallback path and must not weaken its repository-integrity checks.
- The Dashboard is read-only and must not let an app user alter usage evidence or limits.

## Acceptance criteria

- Kimi and Kimi-Swarm refuse launch when weekly usage is 20% or higher.
- Kimi launch refuses missing, malformed, stale, future-dated, or reset-expired usage evidence.
- Weekly Kimi runtime cannot exceed 3,600 seconds; launch timeout is reduced to remaining runtime.
- Actual bounded process time is recorded without storing worker content.
- Codex and dry-run adapters are unaffected.
- Existing approved fallback may classify the guardrail as quota/capacity but still requires unchanged-repository integrity.
- Dashboard displays the current Kimi usage policy and clearly shows allowed or paused state.
- Local snapshot recording validates typed values and writes no secret material.
- All relevant and full tests pass with exact changed paths inside scope.

## Test requirements

- Test valid, at-limit, over-limit, missing, malformed, stale, future and expired snapshots.
- Test runtime period rollover, runtime exhaustion, timeout clamping and atomic recording.
- Test Kimi and Kimi-Swarm block before process launch and Codex remains unaffected.
- Test Dashboard allowed, paused and unavailable states without leaking source exceptions or artifact contents.
- Run focused tests, full `tests/`, compile/import, Streamlit Dashboard smoke, diff/index/scope/new-file checks.

## Constraints

- Preserve `agent_runner` as the authority boundary and GitHub as source of truth.
- Keep the policy provider-neutral in structure while applying the owner-selected limits to Kimi.
- The authenticated reading may be refreshed by Codex desktop, another approved local controller, or a future safe provider adapter; AdvanCore must not depend on one AI vendor for governance.
- Prefer a small reversible implementation and stop for any credential, production, billing or authority need.

## Owner decisions

None. On 23 August 2026 the owner explicitly selected a 20% Kimi weekly allowance limit, a one-hour-per-week Kimi automation runtime limit, Dashboard visibility, and a fresh check before long programs.

## Completion report

### Implemented

Pending implementation.

### Files changed

Pending implementation.

### Database changes

None.

### Tests and results

Pending implementation.

### Assumptions

- "One hour per week" means cumulative local Kimi/Kimi-Swarm process runtime during the same provider week represented by the current usage snapshot.

### Risks / unresolved issues

- Kimi currently has no confirmed stable machine-readable quota API, so an approved local controller must refresh the bounded usage snapshot from an authenticated reading.

### Decisions required

None for this bounded task.

### Recommended next step

Implement the approved guardrail, verify it, then publish the feature branch for independent review.
