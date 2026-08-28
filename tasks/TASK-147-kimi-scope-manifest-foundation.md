# TASK-147 — Kimi Scope Manifest Foundation

STATUS: READY

## Objective

Add a controller-owned `.kimi-scope` manifest that gives a dedicated Kimi or
Kimi Swarm worktree an exact machine-readable copy of the already governed
changed-file scope without granting execution or publication authority.

## Business context

The owner approved a persistent Kimi worktree with an explicit scope manifest.
TASK-145 prevents separately assigned workers from reserving overlapping paths,
and TASK-146 confirms a dedicated worktree is eligible. This task adds only the
bounded manifest artifact; worker-launch integration remains separate.

## In scope

- Add `.kimi-scope` to the repository ignore rules so controller preparation
  does not make an otherwise clean worker worktree appear dirty.
- Add a service that writes schema version, canonical task ID and a unique,
  sorted list of exact repository-relative allowed paths.
- Require canonical paths with no absolute path, wildcard, empty, dot-segment,
  repeated-separator, trailing-slash or case-only duplicates.
- Bind manifest reads and atomic replacement to the verified worktree root;
  reject links, non-regular files, multiple links, unsafe permissions,
  oversized content and malformed saved state.
- Add an exact verification method for the controller to call before and after
  a future Kimi launch.
- Store no prompt, command, environment, output, credential, account, remote,
  business data or approval/publication authority.
- Add deterministic tests and a short runbook.

## Out of scope

- Worker launch or changes to Kimi, Gemini or Codex adapters.
- Worktree creation, cleaning, reset, switching, trust, login or CLI upgrade.
- Task approval, queue claiming, reservation acquisition, fallback routing,
  staging, commit, push, PR, merge, deployment or database changes.
- Automatically deleting a manifest after failure; a stale manifest has no
  authority and must simply fail exact verification for the next task.

## Allowed changed-file scope

- `tasks/TASK-147-kimi-scope-manifest-foundation.md`
- `advancore/agent_runner/kimi_scope_manifest.py`
- `tests/test_kimi_scope_manifest.py`
- `docs/runbooks/KIMI_SCOPE_MANIFEST.md`
- `.gitignore`

## Database impact

None.

## Acceptance criteria

- [ ] The controller can atomically prepare and verify an exact bounded
      `.kimi-scope` manifest without dirtying Git status.
- [ ] Unsafe, aliased, duplicate, malformed or oversized scope data fails
      closed.
- [ ] A stale or changed manifest cannot verify for a different task/scope.
- [ ] The service cannot launch, trust, authenticate, approve or publish.
- [ ] Focused tests, full tests and `git diff --check` pass.

## Owner decisions

Approved on 28 August 2026 as part of the persistent Kimi worker-worktree plan.
This artifact supplements but never replaces task-file scope, TASK-145
reservations, post-run diff verification or `agent_runner` authority.
