# TASK-150 — Real Governed Kimi Swarm Pilot

STATUS: COMPLETE

## Objective

Prove the TASK-143 through TASK-149 launch path with one useful, bounded,
non-database implementation: a deterministic controller-facing formatter for
`PersistentKimiLaunchResult`.

## Required implementation

- Add `advancore/agent_runner/persistent_kimi_reporting.py`.
- Provide `format_persistent_kimi_launch_result(result) -> str`.
- Accept only an actual `PersistentKimiLaunchResult`; reject other values with
  `TypeError` without echoing the supplied value.
- Return deterministic plain text containing only the existing bounded fields:
  status, reason, scope count, changed-path count, worker terminal reason,
  failure classification, return code, elapsed seconds and CLI version.
- Represent absent optional metadata as `not-reported`.
- Do not include repository paths, prompts, commands, PATH values, stdout,
  stderr, credentials, environment values or arbitrary exception text.
- Export the formatter from `advancore.agent_runner`.
- Add deterministic unit tests covering success, preflight failure, worker
  failure, absent metadata and invalid input.
- Extend the persistent-Kimi runbook with a short section explaining that the
  formatter is display-only evidence and grants no execution/publication
  authority.

## Allowed changed-file scope

- `advancore/agent_runner/persistent_kimi_reporting.py`
- `advancore/agent_runner/__init__.py`
- `tests/test_persistent_kimi_reporting.py`
- `docs/runbooks/PERSISTENT_KIMI_LAUNCH.md`

## Constraints

- No database, PostgreSQL, model or Alembic changes.
- No Docker, dependency, authentication, credential, billing or deployment
  changes.
- Do not alter worker routing, approval, fallback, queue, reservation, manifest,
  Git publication or merge behavior.
- Do not stage, commit, push, open a PR or merge.
- Fail closed and stay within the exact allowed changed-file scope.

## Acceptance criteria

- [x] The implementation stays within the exact four-file scope.
- [x] Formatter output is deterministic and contains bounded metadata only.
- [x] Invalid input fails without exposing the input value.
- [x] Focused tests pass.
- [x] Controller postchecks accept the exact-scope worker result.

## Owner decisions

None. The owner approved proceeding with the controlled real Kimi Swarm pilot
after TASK-149 merged into `projects-lifecycle-recovery`.

## Completion report

- Kimi Swarm v0.39.0 completed through the TASK-149 governed service in
  697.819 seconds and changed exactly the four approved files.
- Gemini and Codex fallback workers were not used.
- Bugbot identified two formatter-boundary issues; both were repaired under the
  approved bounded repair cycle, and the final Bugbot review was clean.
- Focused launch and formatter tests: 40 passed.
- Local dependency-independent regression suite: 1,427 passed, 2 skipped.
- `py_compile` and `git diff --check`: passed.
