# TASK-045 — Bounded Standing Authority for Routine Automation

STATUS: REVIEW

## Objective

Record and enforce a controller-owned, time-limited standing authorization for
routine unattended development actions so an owner does not have to approve
every repair, test, independent review, worker fallback, or feature-branch
update separately.

## Business context

The owner explicitly approved the next ten bounded tasks for unattended work
and asked that genuine manual decisions be left for their return. Existing
orchestration correctly preserves approval gates, but it has no machine-readable
way to distinguish routine pre-authorized operations from decisions that must
still pause.

## In scope

- Add a provider-neutral standing-authority service in controller-owned state
  outside every worker repository.
- Bind each authorization to exact task IDs, one non-`main` branch, an expiry,
  a maximum usage count, and an explicit set of routine action classes.
- Permit only worker execution, tests, bounded repair, independent review,
  approved fallback, feature-branch update, PR update, and exception reporting.
- Require an explicit controller assertion that the owner supplied the grant.
- Validate schema, timestamps, identifiers, branch, action, permissions,
  ownership, canonical paths, and non-decreasing bounded usage.
- Use locking and atomic writes; never store prompts, transcripts, credentials,
  environment values, source contents, or provider output.
- Add deterministic tests and a short operating document.

## Explicitly out of scope

- Task approval, implementation approval, controller decisions, merge, `main`,
  deployment, release, production, destructive data actions, billing, compliance
  or commercial rules, and any new credential category.
- Inferring authority from successful tests, worker output, chat text, or an AI
  model.
- Network calls, provider APIs, or dependence on Codex, Kimi, or GitHub clients.

## Allowed changed-file scope

- `tasks/TASK-045-bounded-standing-authority-for-routine-automation.md`
- `advancore/agent_runner/standing_authority.py`
- `advancore/agent_runner/__init__.py`
- `tests/test_standing_authority.py`
- `docs/runbooks/STANDING_AUTHORITY.md`

## Safety requirements

- Missing, malformed, expired, exhausted, conflicting, symlinked, non-owner, or
  overly permissive authority fails closed.
- The worker cannot create, alter, renew, broaden, or consume authority outside
  the controller API.
- A routine grant never satisfies either existing owner/controller approval gate.
- Credential access remains a separately explicit owner decision.

## Acceptance criteria

- Exact authorized routine actions are accepted and atomically counted.
- Wrong task, wrong branch, expired/exhausted policy, unknown action, unsafe
  state, and prohibited approval/publication actions are rejected.
- Ten exact task IDs can be represented without creating open-ended authority.
- Tests prove the artifact contains no secret or worker content.
- Existing orchestration behavior is unchanged until a later task explicitly
  consumes this boundary.

## Database impact

None. State is local, bounded, controller-owned JSON outside Git.

## Owner decisions

None. On 24 August 2026 the owner explicitly approved ten unattended tasks and
accepted task-specific credential injection instead of full environment
inheritance. Manual approval gates must remain for the owner's return.

## Completion report

### Implemented

- Added exact, time-limited, usage-limited routine authority for up to ten named
  tasks on one non-`main` branch.
- Added controller-owned locking, atomic persistence, validation and fail-closed
  consumption outside worker repositories.
- Explicitly excluded approvals, credentials, merge, `main`, deployment,
  destructive actions and business/compliance decisions.
- Added deterministic tests and a plain operating runbook.
- Repaired independent-review findings by binding every grant to the verified
  local Git common directory plus sanitized origin identity (shared worktrees
  only), and normalizing malformed field types into the controlled fail-closed
  error path.
- Repaired the follow-up review finding by recomputing the repository identity
  and checked-out non-`main` branch under the consumption lock rather than
  trusting a cached identity or caller-supplied branch label.
- Repaired the state-location review finding by preserving and checking the
  unresolved path, rejecting every symlinked component and every location
  inside the worker repository, and opening the controller lock with no-follow,
  owner-only validation.

### Files changed

- `tasks/TASK-045-bounded-standing-authority-for-routine-automation.md`
- `advancore/agent_runner/standing_authority.py`
- `advancore/agent_runner/__init__.py`
- `tests/test_standing_authority.py`
- `docs/runbooks/STANDING_AUTHORITY.md`

### Database changes

None.

### Tests executed and results

- Focused standing-authority suite after independent-review repairs: 17 passed.
- Full project suite after independent-review repairs: 813 passed.
- Python compile and `git diff --check`: passed.

### Risks / unresolved issues

- This task establishes the authority boundary but deliberately does not make
  orchestration consume it. TASK-046 will add that bounded integration.
- Manual approval gates remain unresolved for the owner's return as requested.

### Decisions required

- Independent review and eventual implementation approval remain manual.

### Recommended next step

- Implement TASK-046 so the unattended controller consumes routine authority
  while continuing to pause at every excluded owner decision.
