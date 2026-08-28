# TASK-152 — Automatic Worker Fallback Bridge

STATUS: COMPLETE

## Objective

Connect the bounded persistent Kimi launch result to the existing governed
failover checkpoint so the controller can select Gemini next, then Codex, only
after an eligible provider-availability failure and unchanged repository state.

## Required implementation

- Add a pure controller-owned transition service that accepts an existing
  `FailoverCheckpoint`, a `PersistentKimiLaunchResult`, the current repository
  fingerprint, and explicit bounded availability evidence.
- Advance only when the checkpoint currently selects `kimi-swarm`, the launch
  reached the worker and failed for an approved provider-availability reason,
  and the repository fingerprint is unchanged.
- Map only these bounded Kimi outcomes:
  - executable-not-found or spawn failure to `EXECUTABLE_UNAVAILABLE`;
  - quota/capacity terminal evidence to `QUOTA_OR_CAPACITY`;
  - credential-access-required evidence to `AUTHENTICATION_UNAVAILABLE`.
- Select Gemini before Codex through the existing immutable implementation
  route; never repeat Kimi or skip an available approved Gemini worker.
- Fail closed for preflight failures, postcheck failures, successful launches,
  runtime errors, timeout, cancellation, worker exceptions, unknown or
  malformed evidence, repository drift, and an unexpected selected worker.
- Return bounded decision metadata only: whether transition occurred, next
  worker, failure class, and the updated checkpoint. Do not retain prompts,
  commands, paths, environment values, stdout, stderr or arbitrary exceptions.
- Do not launch any worker, consume standing authority, approve output, change
  queue state, write a checkpoint, or perform Git/publication operations.
- Export the new controller service and document how the controller launches
  the selected next worker through the existing authority and integrity gates.
- Add deterministic tests covering eligible Kimi-to-Gemini selection,
  Gemini-unavailable Kimi-to-Codex selection, every blocked failure category,
  malformed evidence, repository drift and route mismatch.

## Allowed changed-file scope

- `advancore/agent_runner/persistent_worker_failover.py`
- `advancore/agent_runner/__init__.py`
- `tests/test_persistent_worker_failover.py`
- `docs/runbooks/WORKER_ROUTING.md`

## Constraints

- No PostgreSQL, database, model, Alembic or Docker changes.
- No dependency installation, virtual environment creation, login, credential,
  billing, deployment or real-data changes.
- Do not modify Streamlit or FastAPI application code.
- Do not launch Kimi, Gemini or Codex from the implementation itself.
- Do not approve, stage, commit, push, open or merge a PR, or touch `main`.
- Preserve `agent_runner` as the authority boundary and fail closed on all
  ambiguity.

## Acceptance criteria

- [x] Eligible Kimi provider failures deterministically select Gemini, then
  Codex only when Gemini has explicit unavailable evidence.
- [x] Unsafe, unknown or repository-changing Kimi outcomes never fall through
  to another worker.
- [x] The bridge stores and returns bounded controller metadata only.
- [x] Focused tests and exact scope verification pass.

## Owner decisions

None. This is the unattended, fail-closed TASK-152 behavior already approved by
the owner.

## Completion report

- Kimi Swarm v0.39.0 implemented the four-file scope first and completed in
  720.266 seconds without Gemini or Codex implementation fallback.
- Bugbot reproduced strict role, explicit Gemini evidence, contradictory
  metadata, forged evidence and malformed-checkpoint privacy defects. Bounded
  controller repairs closed all findings; the final Bugbot review was clean.
- Focused persistent failover, safe failover and bounded reporting tests:
  68 passed.
- Dependency-independent local regression suite: 1,478 passed, 2 skipped.
- `py_compile`, `git diff --check` and exact changed-file scope checks passed.
- The bridge has no worker launch, authority consumption, queue/state write,
  Git mutation, approval or publication capability.
