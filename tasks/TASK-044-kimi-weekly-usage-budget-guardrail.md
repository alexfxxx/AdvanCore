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
- `tests/test_goal_task.py`
- `tests/test_worker_fallback_integration.py`
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

- Added a strict provider-neutral usage snapshot and runtime ledger under the existing Git-ignored `.agent_runner/usage/` boundary.
- Enforced the owner-selected 20% Kimi weekly percentage cap, 3,600-second weekly local runtime cap, and 15-minute reading freshness requirement.
- Added fail-closed Kimi/Kimi-Swarm preflight before process launch, remaining-runtime timeout clamping, and actual elapsed runtime accounting.
- Preserved the existing provider-failure classification and repository-integrity gates for explicitly configured approved fallback.
- Added a read-only Dashboard budget section showing Kimi reported usage, policy cap, local runtime, freshness/reset, and allowed/paused/unavailable state.
- Added a bounded local command to record/show a fresh provider reading without credentials or provider scraping.
- Added an operating runbook separating permanent AdvanCore policy from local authenticated reading refresh by Codex desktop or another approved controller.
- Recorded the current local 44% Kimi reading as PAUSED; the artifact remains ignored and is not part of Git history.

### Files changed

- `tasks/TASK-044-kimi-weekly-usage-budget-guardrail.md`
- `advancore/services/worker_usage_service.py`
- `advancore/agent_runner/worker.py`
- `advancore/pages/dashboard.py`
- `tests/test_worker_usage_service.py`
- `tests/test_worker_usage_guardrail.py`
- `tests/test_dashboard_page.py`
- `tests/test_goal_task.py`
- `tests/test_worker_fallback_integration.py`
- `docs/runbooks/WORKER_USAGE_BUDGET.md`

### Database changes

None.

### Tests and results

- Focused usage, worker, Dashboard, planner, fallback and timeout verification: passed.
- Full project suite with the documented local PostgreSQL configuration: 770 passed.
- Python compile/import and `git diff --check`: passed.
- Streamlit Dashboard AppTest smoke: zero exceptions; rendered Kimi weekly usage 44%, policy limit 20%, and paused state.
- Exact scope, unstaged/staged/new-file and ignored-artifact checks: passed; `.agent_runner/usage/` remains ignored.

### Assumptions

- "One hour per week" means cumulative local Kimi/Kimi-Swarm process runtime during the same provider week represented by the current usage snapshot.
- The refreshed Kimi countdown places the current weekly reset at approximately 28 August 2026 02:39 UTC; a fresh post-reset reading is still required before Kimi can resume.

### Risks / unresolved issues

- Kimi currently has no confirmed stable machine-readable quota API, so an approved local controller must refresh the bounded usage snapshot from an authenticated reading.
- The runtime budget counts local process wall time rather than vendor tokens; the provider percentage remains the primary allowance evidence.
- Local controller-owned evidence is protected by validation and Git isolation, not by a separate operating-system identity; future multi-user deployment requires an authenticated service boundary.

### Decisions required

None for implementation. Independent controller review is still required before publication approval.

### Recommended next step

Commit and publish the verified TASK-044 feature branch for independent controller review; keep Kimi paused until a fresh post-reset reading is recorded.
