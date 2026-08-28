# TASK-144 — Kimi Workspace-Trust Compatibility

STATUS: COMPLETE

## Objective

Restore governed Kimi and Kimi-Swarm startup for separate feature worktrees by
allowing only the non-secret workspace bookkeeping required by Kimi Code v0.38,
without exposing credentials or granting controller authority.

## Business context

Kimi v0.38 resolves and its configuration passes `kimi doctor`, but an isolated
launch exits in about one second with `storage write failed: permission denied`.
Each Git worktree receives a unique Kimi workspace ID. The current sandbox lets
Kimi write sessions, logs, cache and history but not its workspace registry or
the current worktree's trust record.

## In scope

- Derive Kimi's deterministic workspace ID from the resolved worktree path.
- Permit writes to Kimi's non-secret workspace registry and only the current
  worktree's trust record required for startup.
- Permit the Kimi CLI to refresh only its own existing `oauth/kimi-code` token
  and use its matching non-secret lock file; no GitHub, database, Codex, Gemini,
  SSH or other credential is allowed.
- Permit atomic synchronization of only Kimi's matching
  `credentials/kimi-code.json` mirror while keeping every other credential path
  outside the allowlist.
- Keep credential, OAuth, plugin, skill, update, Git metadata, controller state,
  environment-secret and unrelated-home protections unchanged.
- Add tests proving other workspace-trust records remain outside the allowlist.
- Run a no-file-change governed Kimi smoke test, followed by a bounded Swarm
  capability test only if ordinary Kimi startup succeeds.
- Preserve fail-closed fallback and telemetry behavior.

## Out of scope

- Sharing controller/GitHub/database credentials or arbitrary environment data.
- Allowing all of `~/.kimi-code`, all home-directory writes, or unrelated
  workspace trust records.
- Database changes, migrations, real-data imports, billing, deployment or main.
- Automatically approving or publishing Kimi output.

## Allowed changed-file scope

- `tasks/TASK-144-kimi-workspace-trust-compatibility.md`
- `advancore/agent_runner/worker.py`
- `tests/test_worker_usage_guardrail.py`
- `tests/test_worker_execution_telemetry.py`
- `docs/runbooks/WORKER_ROUTING.md`

## Database impact

None.

## Acceptance criteria

- [x] An isolated Kimi smoke test starts and exits successfully without changing
      repository files.
- [x] Kimi-Swarm capability is probed only after ordinary Kimi succeeds.
- [x] Only the current worktree's trust record and required non-secret registry
      are writable; credentials and unrelated trust records remain protected.
- [x] Existing worker order, governance, scope and publication gates remain.
- [x] Focused tests, full tests and `git diff --check` pass.

## Owner decisions

The owner explicitly approved testing and repairing Kimi usage on 28 August
2026, with the goal of using Kimi Agent Swarm. Kimi may refresh only its own
existing OAuth token; this approval does not grant Kimi controller authority or
access to any other credential.

## Completion report

### Implemented

- Restored Kimi v0.38 startup in separate governed Git worktrees with exact
  workspace registry/trust bookkeeping and atomic temporary-file patterns.
- Permitted only Kimi's own OAuth token, matching lock and credential mirror to
  refresh; other credentials, environment secrets and controller variables are
  neither inherited nor added to the write allowlist.
- Added fail-closed preflight checks for the fixed owner-home executable,
  pre-warmed authentication and existing current/ancestor workspace trust.
- Added isolated version telemetry reporting `Kimi v0.38.0`.
- Proved the unsupported `KIMI_CODE_AGENT_SWARM_MAX_CONCURRENCY` variable is not
  inherited on v0.38.0.

### Live verification

- Final ordinary Kimi smoke: exit 0 in 9.36 seconds; repository unchanged.
- Final Agent Swarm test: exit 0 in 84.70 seconds; repository unchanged.
- Kimi session evidence contained a main agent plus `agent-0` and `agent-1`,
  confirming that two Swarm sub-agents genuinely ran.
- Raw prompts, output, PATH and credentials were not added to durable telemetry.

### Database changes

None.

### Automated verification

- Focused worker, telemetry and runner tests: 89 passed.
- Full isolated suite: 1,269 passed, 2 skipped.
- `git diff --check`: passed.

### Known bounded warning

Kimi's optional query-store mirror attempts a hard-link operation inside its
cache. The sandbox continues to block all hard links because allowing them could
bypass protected-file read boundaries. Kimi and Agent Swarm both completed
successfully despite this nonfatal cache warning.

### Decisions required

None for local completion. Independent review and publication remain required.
