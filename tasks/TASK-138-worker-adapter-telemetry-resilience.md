# TASK-138 — Worker Adapter and Telemetry Resilience

STATUS: APPROVED

## Objective

Make Kimi and Gemini worker failures diagnosable without weakening the
`agent_runner` authority boundary: preserve the existing Kimi owner-home
executable fallback and Gemini `--print=<prompt>` invocation, distinguish
pre-spawn failures from post-spawn runtime failures, and record bounded timing
and CLI context in the local runner audit.

## Confirmed facts

- Kimi Code 0.38.0 is installed at `~/.kimi-code/bin/kimi` but is not available
  on the controller shell's normal `PATH`.
- The production adapter already checks normal `PATH` first and then the fixed,
  non-symlink owner-home Kimi path.
- The installed Gemini/Antigravity CLI is `agy` 1.1.22. Its local help confirms
  `--print`, `--mode accept-edits`, `--sandbox`, JSON output and the existing
  timeout flags are valid.
- The Gemini adapter already encodes the instruction as one
  `--print=<prompt>` argument.
- Non-zero worker exits currently retain stdout/stderr in memory but report only
  a generic message and default terminal reason. Audit records do not show
  elapsed time, executable resolution source, CLI version or spawn/runtime
  classification.

## In scope

- Keep PATH-first Kimi resolution with the fixed owner-home fallback and return
  an explicit `EXECUTABLE_NOT_FOUND` classification when neither is usable.
- Preserve the verified Gemini 1.1.22 argument vector and add regression tests
  that prevent a standalone prompt or ambiguous `--print` form.
- Classify failures before binary load as `SPAWN_ERROR` and failures after a
  successful spawn as `RUNTIME_ERROR`; preserve the existing timeout,
  cancellation and provider-fallback semantics.
- Capture worker start, finish and monotonic elapsed duration.
- Attach the resolved executable, safe resolution source and minimal runtime-path
  profile to the in-memory result. Keep CLI version optional and do not launch a
  second, less-isolated provider process merely to discover it.
- Add only safe, bounded worker metadata to local audit records. Raw prompts,
  command arguments, environment values and stdout/stderr must not be persisted.
- Add deterministic unit tests for resolution, argument construction,
  spawn/runtime classification, captured streams and safe audit projection.
- Update the worker-routing runbook with the monitoring semantics.

## Out of scope

- PostgreSQL models, connection settings, business data or Alembic migrations.
- Streamlit, FastAPI or frontend changes.
- Installing, upgrading or authenticating provider CLIs.
- Provider quota scraping, billing, model selection, arbitrary worker flags or
  changes to the Kimi → Gemini → Codex route.
- Persisting a full command, prompt, raw `PATH`, environment dump, OAuth data,
  stdout or stderr because those can contain credentials or business data.
- Publication, deployment or any merge to `main`.

## Allowed changed-file scope

- `tasks/TASK-138-worker-adapter-telemetry-resilience.md`
- `advancore/agent_runner/worker.py`
- `advancore/agent_runner/audit.py`
- `advancore/agent_runner/runner.py`
- `advancore/agent_runner/auto_pipeline.py`
- `tests/test_worker_execution_telemetry.py`
- `tests/test_agent_runner.py`
- `tests/test_gemini_worker_foundation.py`
- `tests/test_worker_fallback.py`
- `docs/runbooks/WORKER_ROUTING.md`

## Database impact

None.

## Acceptance criteria

- [ ] Kimi resolves from PATH or the governed owner-home fallback and missing
      resolution fails once with `EXECUTABLE_NOT_FOUND`.
- [ ] Gemini uses exactly one `--print=<prompt>` argument with its existing
      verified safety flags.
- [ ] Launch exceptions and executable-style exits are `SPAWN_ERROR`; other
      non-zero exits, timeout and cancellation are `RUNTIME_ERROR`.
- [ ] Non-zero results retain raw stdout/stderr only in memory for immediate
      bounded classification.
- [ ] Audit metadata reports timing, exit code, terminal reason, failure class
      and executable resolution without raw command, prompt, PATH, stdout,
      stderr, credentials or business content. Optional CLI-version evidence is
      never collected through an unisolated provider launch.
- [ ] Existing fail-closed isolation, credential screening, repository checks,
      approval gates and worker order remain unchanged.
- [ ] Focused tests, full tests and `git diff --check` pass.

## Owner decisions

None. The owner approved this bounded repair and requested Bugbot review on
28 August 2026.
