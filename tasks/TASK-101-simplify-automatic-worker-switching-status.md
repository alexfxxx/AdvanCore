# TASK-101 — Simplify Automatic Worker Switching Status

STATUS: APPROVED

## Objective

Replace Dashboard usage and balance detail with plain authentication readiness, known current or selected worker status, and bounded recent notifications for actual automatic worker switches while preserving the fixed Kimi-Swarm to Gemini to Codex route and every existing runner protection.

## Business context

The current Dashboard exposes provider balance, weekly percentage, token-count, evidence-freshness, and usage-availability details that do not reliably help the owner understand whether governed work can proceed. The owner needs a simpler operational view that explains authentication readiness, identifies the worker selected or running when known, and reports genuine automatic handoffs without treating unreadable balance evidence as a blocker.

## Facts

- The implementation route is fixed as Kimi-Swarm, then Gemini, then Codex.
- Automatic continuation is limited to classified executable, authentication, quota or limit, and capacity failures.
- Unknown failures, timeouts, cancellations, unsafe or ambiguous actions, and Git-integrity changes remain stop conditions.
- The Dashboard currently displays provider balance, weekly percentage, token-count, stale-evidence, and usage-availability information.
- Bounded non-generative authentication readiness checks already exist for Kimi, Gemini, and Codex.
- Unreadable provider balance alone must neither be displayed nor prevent governed work.
- Agent-runner authority, standing-authority consumption, fallback authority, credential screening, repository and Git-integrity verification, database protections, production protections, and main protections must remain unchanged.
- No database, credential, billing, deployment, or main changes are authorised.

## Assumptions

- Existing authentication readiness results can supply the simplified Dashboard authentication messages without adding provider account access or generative checks.
- Existing worker-selection and automatic-pipeline results contain, or can safely expose, the bounded worker names and classified switch reasons needed for Dashboard presentation.
- Recent handoff notifications can remain session-local or controller-owned non-database evidence and do not require durable operational database storage.
- A bounded recent-notification list means only genuine attempted-worker transitions from the fixed route, not route previews or hypothetical fallbacks.
- The existing AI usage service may remain internally available where required by runner guardrails, provided the removed usage and balance facts are no longer presented by the Dashboard and unreadable balance alone does not affect routing.

## In scope

- Remove provider balance, weekly percentage, token-count, stale-evidence, and usage-availability displays and related explanatory text from the Dashboard.
- Present plain-language authentication readiness for Kimi, Gemini, and Codex using bounded non-generative readiness evidence.
- Show the current worker or selected worker when that fact is known from controller-owned runtime or selection evidence, and show neutral wording when it is not known.
- Add a bounded recent handoff notification view containing only actual worker transitions, their classified reason category, and safe timing or ordering metadata.
- Use plain-language handoff explanations for actual limit or quota, authentication, executable, and capacity switches without exposing raw provider output.
- Ensure unreadable, missing, stale, or unavailable balance evidence alone neither appears on the Dashboard nor blocks worker selection, launch, or continuation.
- Preserve the fixed Kimi-Swarm to Gemini to Codex route, the maximum attempt boundary, non-repetition, eligible-failure classification, and integrity checks before every handoff.
- Add deterministic tests for simplified Dashboard rendering, known and unknown worker state, bounded handoff notifications, eligible switch reasons, and unreadable-balance non-blocking behavior.
- Update the worker-routing and Dashboard runbook documentation to describe the simplified status model and retained governance boundaries.

## Explicitly out of scope

- Changing the fixed worker order or adding another worker attempt.
- Changing worker registration, role eligibility, launch commands, provider adapters, or model selection.
- Weakening or bypassing agent-runner authority, standing-authority consumption, fallback authority, credential screening, environment isolation, timeout handling, or repository and Git-integrity checks.
- Allowing continuation after unknown failure, timeout, cancellation, unsafe or ambiguous action, repository mutation, or a genuine owner-decision stop.
- Collecting, reading, storing, displaying, or modifying credentials, secrets, tokens, OAuth material, account identifiers, or raw provider output.
- Provider account scraping, balance polling, quota estimation, billing access, credit purchase, or commercial-policy changes.
- Database schema changes, migrations, database data changes, or production-data access.
- Production release activity, deployment activity, or changes to protected main behavior.
- Adding persistent notification storage outside the existing bounded controller evidence model.
- Broad redesign of the Dashboard, AI Center, routing architecture, or agent runner.

## Allowed changed-file scope

- `advancore/pages/dashboard.py`
- `advancore/services/worker_auth_readiness_service.py`
- `advancore/services/worker_route_preview_service.py`
- `advancore/services/worker_routing_evidence_service.py`
- `advancore/services/ai_usage_dashboard_service.py`
- `advancore/agent_runner/auto_pipeline.py`
- `docs/runbooks/WORKER_ROUTING.md`
- `docs/runbooks/AI_USAGE_DASHBOARD.md`
- `tests/test_dashboard_page.py`
- `tests/test_worker_auth_readiness_service.py`
- `tests/test_worker_route_preview_service.py`
- `tests/test_worker_routing_evidence_service.py`
- `tests/test_ai_usage_dashboard_service.py`
- `tests/test_worker_fallback.py`

## Database impact

None

## Safety requirements

- GitHub remains the source-of-truth.
- `main` remains untouched and non-executable unless explicitly approved.
- Worker/swarm cannot approve its own work.
- No automatic staging, commit, push, merge, tag, deploy, switch, reset,
  rebase, or history rewrite.
- This generated task is DRAFT and cannot execute until a valid
  `DRAFT -> READY` controller/owner transition.
- Unknown, unsafe, malformed, conflicting, or ambiguous states fail closed.
- The planner proposed only; the runner constructed this DRAFT; the
  controller/owner must authorize execution.

## Acceptance criteria

- The Dashboard contains no provider balance, weekly percentage, token-count, stale-evidence, or usage-availability display.
- The Dashboard reports each provider's authentication readiness in plain language without displaying raw command output, credentials, tokens, account identifiers, or provider error details.
- The Dashboard identifies the current or selected implementation worker when controller-owned evidence makes it known and does not guess when it is unknown.
- Recent handoff notifications represent only actual automatic switches and are bounded in count.
- Each handoff notification identifies the previous worker, next worker, and one safe plain-language reason corresponding to limit or quota, authentication, executable, or capacity failure.
- Route previews, missing balance readings, stale balance readings, and unavailable usage readings do not generate handoff notifications.
- Unreadable balance evidence alone neither disables a worker nor prevents selection, launch, or continuation.
- The implementation route remains exactly Kimi-Swarm, Gemini, then Codex, with no repeated worker and no fourth attempt.
- All existing authority consumption, credential safety, Git-integrity, repository, timeout, database, production, and main safeguards remain effective.
- No database, migration, credential, billing, deployment, or production behavior is changed.
- The routing and Dashboard runbooks accurately describe the simplified status, actual-switch notification semantics, unreadable-balance behavior, and retained stop conditions.
- Relevant focused tests and the full regression suite pass, and a completion report records the required governance sections.

## Test requirements

- Add deterministic Dashboard tests proving all removed usage and balance labels and values are absent.
- Add deterministic Dashboard tests for authenticated, login-required, and unavailable authentication readiness wording.
- Add deterministic tests for displaying a known selected or current worker and neutral handling when no worker is known.
- Add deterministic tests that actual Kimi-Swarm to Gemini and Gemini to Codex switches produce bounded notifications with the correct classified reason.
- Add deterministic tests for each permitted notification category: limit or quota, authentication, executable, and capacity.
- Add deterministic tests proving unknown failures, timeouts, cancellations, unsafe conditions, and Git-integrity changes still stop without an automatic handoff.
- Add deterministic tests proving missing, malformed, stale, or unreadable balance evidence alone does not block an otherwise eligible worker.
- Add tests proving route previews and authentication readiness refreshes do not create false handoff notifications.
- Add tests proving notification payloads and rendered messages exclude raw provider output, credentials, tokens, account identifiers, prompts, responses, environment values, and repository paths.
- Run the focused Dashboard, authentication-readiness, routing-evidence, route-preview, usage-service, and fallback test modules.
- Run the full automated test suite and a repository whitespace validation check.

## Constraints

- Treat this proposal as planning assistance only; implementation requires separate controller or owner authorisation.
- Preserve the fixed Kimi-Swarm to Gemini to Codex route and all existing role restrictions.
- Do not weaken agent-runner authority or grant workers any new authority.
- Consume existing standing and fallback authority at the same governed points as before.
- Verify repository, index, worktree, HEAD, branch, and remotes according to the existing integrity contract before any automatic handoff.
- Do not treat unreadable balance as evidence of exhaustion or as a launch failure.
- Derive switch notifications only from classified runtime outcomes, never from inferred provider state or Dashboard observations.
- Keep notification evidence bounded, non-secret, provider-neutral, and free of prompts, responses, transcripts, raw errors, environment values, credentials, and customer data.
- Do not access or modify credentials, tokens, OAuth sessions, billing settings, provider accounts, production data, or production systems.
- Do not introduce database storage or migrations.
- Do not perform deployment or modify protected main behavior.
- Keep changes small, reversible, and confined to the allowed changed-file scope.
- Preserve working functionality not explicitly changed by this task.
- Document assumptions, risks, test results, and unresolved issues in the eventual completion report.

## Owner decisions

- Approved on 26 August 2026: read only existing bounded controller-owned audit
  receipts across application sessions so the owner can see genuine automatic
  switches that occurred while the Dashboard was closed. Do not add a new
  database or provider-side source.
- Approved on 26 August 2026: show at most the five most recent genuine
  handoffs from the preceding seven days. Exclude older receipts and all route
  previews, raw errors, prompts, responses, credentials, account identifiers,
  environment values, and repository paths.

## Completion report

### Implemented

- Replaced Dashboard balance, percentage, token, evidence-age, and
  usage-availability cards with a plain automatic-worker status section.
- Preserved the fixed Kimi-Swarm to Gemini to Codex route and recorded only
  successful adjacent handoffs produced by eligible, integrity-checked
  fallback decisions.
- Added a bounded reader that shows the latest selected worker when known and
  at most five genuine handoffs from the preceding seven days.
- Added safe reason labels for executable, authentication, limit or quota, and
  provider-capacity switches without rendering raw worker output.
- Kept start-of-day non-generative authentication readiness and all existing
  runner authority, credential, Git, database, production, and protected-main
  boundaries unchanged.
- Made the runner's pytest launcher use the active Python interpreter when a
  worktree-local virtual environment is absent.

### Files changed

- `advancore/agent_runner/auto_pipeline.py`
- `advancore/pages/dashboard.py`
- `advancore/services/worker_routing_evidence_service.py`
- `docs/runbooks/AI_USAGE_DASHBOARD.md`
- `docs/runbooks/WORKER_ROUTING.md`
- `tests/test_dashboard_page.py`
- `tests/test_worker_fallback.py`
- `tests/test_worker_routing_evidence_service.py`
- `tasks/TASK-101-simplify-automatic-worker-switching-status.md`

### Database changes

None. No migration, operational row, credential, billing, provider account,
deployment, production, or `main` change was made.

### Tests executed and results

- Focused Dashboard, authentication, route-preview, routing-evidence,
  usage-dashboard, fallback, and auto-pipeline tests: 125 passed.
- Full suite against an in-memory test database: 1,127 passed and 2 skipped.
  The two PostgreSQL migration tests intentionally run only in GitHub Actions.
- Python compilation and `git diff --check`: passed.

### Assumptions

- Cross-session notifications read the existing `.agent_runner` auto-pipeline
  receipts belonging to the repository from which the local app is running.
- "Most recently selected" is historical controller evidence and is not
  presented as proof that a worker process is currently running.

### Risks / unresolved issues

- Different independent worktrees keep separate Git-ignored controller
  receipts. A switch made in another worktree will not appear until the app and
  orchestration use a shared governed execution checkout or a separately
  approved machine-wide notification contract.
- Provider balance services remain in the codebase for internal guardrails and
  compatibility, but their figures are no longer presented on the Dashboard.

### Decisions required

None for TASK-101 implementation review. Publication must still target
`projects-lifecycle-recovery`, never `main`.

### Recommended next step

Obtain independent review, then approve controller-gated publication of the
feature branch into a PR targeting `projects-lifecycle-recovery`.
