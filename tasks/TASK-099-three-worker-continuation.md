# TASK-099 — Three-Worker Automatic Continuation

STATUS: REVIEW

## Objective

Continue eligible clean implementation work automatically through the fixed
owner-approved order `Kimi-Swarm → Gemini → Codex` instead of stopping when one
provider is unavailable.

## In scope

- Make the implementation preference order Kimi-Swarm, Gemini, then Codex.
- Extend the governed auto-pipeline from one fallback to at most two fallbacks.
- Require eligible provider failure classification and unchanged repository,
  index, branch, HEAD, worktree, and remotes before every handoff.
- Never repeat a worker and record every bounded handoff in audit output.
- Consume standing fallback/worker authority immediately before each launch.
- Use the fixed three-worker route for unattended orchestration.
- Keep manual one-fallback CLI behavior backward compatible.
- Update Dashboard/AI Center wording, runbooks, and deterministic tests.

## Out of scope

Fallback after unknown failure, timeout, cancellation, repository mutation,
credential-risk input, unsafe/ambiguous action, owner decision, destructive
database operation, deployment, production/`main`, billing, or credential
changes.

## Allowed changed-file scope

- `tasks/TASK-099-three-worker-continuation.md`
- `advancore/agent_runner/auto_pipeline.py`
- `advancore/agent_runner/worker_routing.py`
- `advancore/agent_runner/failover.py`
- `advancore/agent_runner/orchestration.py`
- `advancore/agent_runner/worker_rehearsal.py`
- `advancore/pages/ai_center.py`
- `advancore/services/ai_usage_dashboard_service.py`
- `advancore/services/candidate_readiness_service.py`
- `docs/runbooks/WORKER_ROUTING.md`
- `docs/validation/MULTI_WORKER_GOVERNANCE_REHEARSAL.md`
- `tests/test_governed_worker_selection.py`
- `tests/test_safe_failover.py`
- `tests/test_worker_routing.py`
- `tests/test_worker_route_preview_service.py`
- `tests/test_worker_fallback.py`
- `tests/test_worker_fallback_integration.py`
- `tests/test_orchestration.py`
- `tests/test_multi_worker_rehearsal.py`
- `tests/test_ai_center_page.py`
- `tests/test_ai_usage_dashboard_service.py`
- `tests/test_candidate_readiness_service.py`
- `tests/test_dashboard_page.py`

## Database impact

None.

## Acceptance criteria

- [x] The immutable implementation order is Kimi-Swarm, Gemini, Codex.
- [x] Kimi eligible failure can hand off to Gemini without owner presence.
- [x] Gemini eligible failure can hand off to Codex without owner presence.
- [x] Unknown failure, timeout, cancellation, or any Git integrity change stops.
- [x] Every launch consumes existing standing authority and every handoff
      consumes approved-fallback authority.
- [x] Unreadable subscription balance alone does not stop or disable a worker.
- [x] No worker repeats and no fourth attempt is possible.
- [x] Existing one-fallback callers remain compatible.
- [x] Focused and full tests plus `git diff --check` pass.

## Owner decisions

Approved on 26 August 2026: use Kimi first, Gemini second, and Codex last. Do
not stop the overall job merely because one provider reaches a usage limit or
has no readable balance; continue to the next approved worker. Preserve all
security, integrity, destructive-action, production, `main`, and genuine owner
decision stops.

## Completion report

### Implemented

- Set the immutable implementation order to Kimi-Swarm, Gemini, then Codex.
- Extended the auto-pipeline to accept the fixed two-fallback continuation route
  while retaining the existing one-fallback API.
- Rechecked failure classification and complete Git integrity before each hop.
- Recorded both handoffs in result, report, and bounded audit payloads.
- Applied the fixed three-worker route to unattended orchestration with standing
  authority consumed separately for every worker and fallback launch.
- Extended safe failover checkpoints and offline rehearsal to three workers.
- Updated AI Center, Dashboard status text, and routing documentation.

### Database and credentials

No database, migration, credential, OAuth, billing, deployment, or `main`
change. No external AI request was made during implementation or testing.

### Verification

- Focused routing/orchestration/UI tests: 145 passed.
- Full suite: 1,120 passed and 2 skipped.
- Python compilation and `git diff --check`: passed.

### Assumptions and risks

- Only classified executable, authentication, quota, or capacity failures are
  eligible for continuation.
- Unknown failure, timeout, cancellation, unsafe input, or any repository/index/
  branch/HEAD/remote mutation remains terminal and requires attention.
- TASK-099 is stacked on TASK-098 and TASK-097 and must be reviewed/merged in
  dependency order.

### Decisions required and next step

No further routing decision is required. Obtain independent review, then merge
the stacked PRs into `projects-lifecycle-recovery` in order; never merge them
directly to `main`.
