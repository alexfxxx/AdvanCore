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
- The installed Kimi CLI exposes the usage reading interactively rather than through a confirmed stable machine-readable command.
- `agent_runner` remains the authority boundary and already supports explicitly approved worker fallback.
- `.agent_runner/` is local and Git-ignored, but worker usage authority must not be stored inside that worker-writable tree.

## In scope

- Add a provider-neutral, OS-account-wide local usage snapshot contract in controller-owned state outside every worker repository, with strict validation and no credentials.
- Add a Kimi policy of 20% provider-reported weekly usage and 3,600 seconds local runtime per provider week.
- Require a fresh, unexpired usage snapshot before every Kimi or Kimi-Swarm implementation/planner launch; stale, missing, malformed, reset-expired, at-limit, or runtime-exhausted state must block before process launch.
- Bound a Kimi launch timeout to the remaining weekly runtime and record actual elapsed Kimi process time in a separate local runtime ledger.
- Return a quota/capacity-classifiable failure so an already configured approved fallback may be considered through the existing integrity checks.
- Show Kimi reported usage, policy cap, runtime, reset, freshness and allowed/paused state on the Dashboard.
- Provide a small local snapshot-recording command in the usage service module for an approved controller/operator to refresh the provider reading.
- Automatically request a fresh bounded reading from a fixed controller-owned probe when evidence is missing, stale or reset-expired; validate its executable and exact JSON contract before accepting it.
- Document which capability is permanent AdvanCore policy and which local controller action refreshes the authenticated provider reading.
- Add deterministic service, worker and Dashboard tests.

## Explicitly out of scope

- Scraping Kimi websites, storing Kimi credentials, automating Kimi login, accepting worker-selected refresh commands, or claiming a stable Kimi quota command exists.
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
- Serialize Kimi launches with an exclusive controller lock, reserve bounded runtime before launch, and retain the full reservation after an ambiguous interruption.
- Preserve a stable provider-period identity across small reset-time adjustments; provider usage and charged runtime must not decrease within that period.
- Fingerprint evidence across worker execution and quarantine any unexpected alteration.
- Require an approved OS write-isolation boundary around controller state for Kimi and all descendants; fail closed before reservation if isolation is unavailable.
- Prove the OS isolation profile can actually start before refreshing or reserving usage; executable presence alone is insufficient.
- Reject symlinked, hard-linked, non-owner, or writable aliases anywhere in the controller probe path so a worker cannot substitute the refresh executable.
- Bound both probe output streams while reading them, terminate oversized or timed-out probe process groups, and reject invalid bytes without escaping the fallback-eligible fail-closed result.
- Restrict Kimi and descendants to writes inside the governed repository, a per-launch temporary directory, and documented non-executable Kimi session/cache/log/history paths; explicitly deny controller state, Kimi executables, credentials, plugins, skills, updates, Homebrew and `/usr/local`.
- Resolve the Kimi executable before sandbox launch, fix Kimi's data-home and temporary paths from controller-owned values, disable telemetry for governed runs, and give the usage probe only the immutable `/usr/bin:/bin` search path.
- Share one provider ledger and lock across all local AdvanCore clones/worktrees.
- Clamp launches to a guarded pre-reset deadline and carry any unexpectedly cross-reset charge into the next verified provider period.
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
- Missing or stale evidence is automatically refreshed through a fixed, owner-only controller probe; invalid, missing or unsafe probes fail closed and permit only the existing approved fallback path.
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

- Added a strict provider-neutral usage snapshot and runtime ledger in controller-owned state outside the Git repository and worker workspace.
- Enforced the owner-selected 20% Kimi weekly percentage cap, 3,600-second weekly local runtime cap, and 15-minute reading freshness requirement.
- Added fail-closed Kimi/Kimi-Swarm preflight before process launch, remaining-runtime timeout clamping, and actual elapsed runtime accounting.
- Preserved the existing provider-failure classification and repository-integrity gates for explicitly configured approved fallback.
- Added a read-only Dashboard budget section showing Kimi reported usage, policy cap, local runtime, freshness/reset, and allowed/paused/unavailable state.
- Added a bounded local command to record/show a fresh provider reading without credentials or provider scraping.
- Added automatic missing/stale-reading refresh through a fixed owner-only controller probe with a strict bounded JSON contract and sanitized environment.
- Added an operating runbook separating permanent AdvanCore policy from local authenticated reading refresh by Codex desktop or another approved controller.
- Preserved fail-closed behavior during the schema transition: the legacy 44% reading is not trusted or silently promoted into the new controller-owned schema, so Kimi remains unavailable until an approved controller records a fresh reading.
- Repaired independent-review findings by adding a stable period identifier, non-decreasing same-period evidence, exclusive launch locking, pre-launch timeout reservation, crash-safe charging, evidence fingerprinting, and fail-closed quarantine.
- Repaired the second independent-review findings by moving to one OS-account-wide ledger, placing Kimi and its descendants under macOS write denial for controller state, failing closed without isolation, bounding launches before reset, and carrying delayed cross-reset charges forward.
- Rechecked the absolute provider-reset deadline immediately before process creation so slow repository verification cannot start Kimi after the fresh-reading boundary.
- Replaced the sandbox executable-presence check with a real pre-reservation capability probe, so nested-sandbox denial is classified before Kimi is invoked and the approved fallback can run.
- Repaired the fourth independent-review findings by validating the full probe path against symlink/hard-link aliases and collecting both probe output streams under strict byte, time, decoding and process-lifecycle bounds.
- Repaired the fifth independent-review finding by replacing broad filesystem write permission with a repository-and-reviewed-runtime allowlist, explicit executable/credential denials, per-launch scratch isolation, absolute worker executable resolution, and an immutable usage-probe command search path.
- Repaired the sixth independent-review finding by replacing controller-environment inheritance with a minimal fixed Kimi runtime environment. Unrelated provider, GitHub, database, proxy and loader variables no longer cross the worker boundary; future task-required credentials require a separately approved capability boundary.
- Repaired the seventh independent-review finding by normalizing bounded JSON parser depth and integer-limit failures at both probe and stored-evidence boundaries into the existing fail-closed usage result, preserving approved fallback eligibility.

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

- Seventh-repair focused usage, guardrail and fallback verification: 53 passed.
- Seventh-repair full project suite with the documented local PostgreSQL configuration: 798 passed.
- Sixth-repair focused usage, worker, fallback and task verification: 75 passed.
- Sixth-repair full project suite with the documented local PostgreSQL configuration: 796 passed.
- Sixth-repair Python compile and `git diff --check`: passed.
- Fifth-repair focused usage, worker, Dashboard, fallback, timeout and task verification: 115 passed.
- Full project suite with the documented local PostgreSQL configuration: 796 passed.
- Python compile/import and `git diff --check`: passed.
- Streamlit Dashboard AppTest smoke: zero exceptions; rendered Kimi usage unavailable, policy limit 20%, and the fail-closed refresh warning expected during secure-schema transition.
- Exact scope, unstaged/staged/new-file and controller-state checks: passed; authoritative usage evidence is outside Git and shared across checkouts.

### Assumptions

- "One hour per week" means cumulative local Kimi/Kimi-Swarm process runtime during the same provider week represented by the current usage snapshot.
- The refreshed Kimi countdown places the current weekly reset at approximately 28 August 2026 02:39 UTC; a fresh post-reset reading is still required before Kimi can resume.

### Risks / unresolved issues

- Kimi currently has no confirmed stable machine-readable quota command. A one-time reviewed local probe must bridge the authenticated Kimi client to AdvanCore's bounded JSON contract; thereafter `agent_runner` refreshes missing/stale readings automatically.
- The runtime budget counts local process wall time rather than vendor tokens; the provider percentage remains the primary allowance evidence.
- Controller evidence is outside every worker repository, shared across local checkouts, lock-serialized, fingerprint-checked, and protected from Kimi writes by the approved macOS sandbox. A future multi-user or remotely hosted worker deployment still requires a reviewed platform-specific isolation or authenticated service boundary.
- The current approved Kimi isolation adapter is macOS-specific. On a platform without an approved equivalent, Kimi pauses before launch and an already approved fallback may be considered.
- The secure version-2 evidence store intentionally starts unavailable rather than importing the stale version-1 reading; a fresh authenticated Kimi reading is required before Kimi can resume.

### Decisions required

None for implementation. Independent controller review is still required before publication approval.

### Recommended next step

Commit and publish the repaired TASK-044 feature branch, then rerun independent Bugbot review before merge. Kimi Code is now authenticated locally, but the current live weekly reading is 44%, so the 20% policy continues to require Codex fallback until the provider resets and the reviewed probe records a fresh below-limit reading.
