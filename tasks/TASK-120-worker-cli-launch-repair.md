# TASK-120 — Worker CLI Launch Repair

STATUS: APPROVED

## Objective

Repair the confirmed local Kimi executable-discovery and Gemini prompt-argument
defects so the existing governed worker route can launch the installed,
authenticated CLIs without weakening worker isolation or approval boundaries.

## Business context

TASK-119 attempted the approved Kimi-Swarm, Gemini, Codex worker sequence. Kimi
was classified as executable-unavailable even though Kimi Code 0.38.0 is
installed at the controller-owned fixed path. Gemini/Antigravity 1.1.21 was
authenticated but exited with code 2 because the adapter supplied `--print` as
a separate flag before other options, causing `agy` to treat `--mode` as the
prompt. Codex completed the work, but the first two workers must be reliable.

## Facts

- `~/.kimi-code/bin/kimi --version` reports 0.38.0 and `kimi doctor` passes.
- Kimi is not discoverable through the current restricted shell PATH.
- AdvanCore's authentication readiness probe already recognizes the fixed Kimi
  installation and reports it authenticated.
- `agy --version` reports 1.1.21 and the readiness probe reports authenticated.
- The exact Gemini adapter command fails before model execution with the local
  CLI error that `--print` consumed `--mode` as its prompt.
- `agy --print=<prompt>` is the supported unambiguous argument form.

## In scope

- Resolve production Kimi/Kimi-Swarm launches from the fixed owner-home
  `~/.kimi-code/bin/kimi` path when normal PATH discovery fails.
- Preserve custom executable overrides only as the existing test seam.
- Encode the Gemini prompt as one `--print=<prompt>` argument while retaining
  the existing sandbox, accept-edits, slash-disable, JSON output, timeout and
  new-project flags.
- Add regression tests for fixed-path Kimi discovery, missing-executable
  fail-closed behavior and the corrected Gemini argument vector.
- Run harmless disposable smoke prompts for Kimi and Gemini after unit/full
  verification, without modifying the AdvanCore repository.
- Document the confirmed launch behavior in the existing worker-routing runbook.

## Out of scope

- Changing the Kimi 20% weekly or 60-minute runtime policy.
- Adding an unverified swarm-concurrency environment variable.
- Installing, upgrading or authenticating any CLI.
- Selecting caller-controlled model, temperature, agent, plugin, endpoint or
  arbitrary command options.
- Changing prompts to embed repository file contents.
- Business feature work, database changes, deployment, `main`, or credentials.

## Allowed changed-file scope

- `tasks/TASK-120-worker-cli-launch-repair.md`
- `advancore/agent_runner/worker.py`
- `tests/test_agent_runner.py`
- `tests/test_auto_pipeline.py`
- `tests/test_gemini_worker_foundation.py`
- `docs/runbooks/WORKER_ROUTING.md`

## Database impact

None.

## Acceptance criteria

- [x] A registered Kimi/Kimi-Swarm adapter uses PATH discovery when available.
- [x] When PATH lacks Kimi, the registered adapter uses only the fixed
      owner-home `.kimi-code/bin/kimi` executable when it is a regular
      executable file.
- [x] Missing or unsafe Kimi candidates continue to fail closed.
- [x] Gemini passes the full bounded instruction through one
      `--print=<prompt>` argument and retains all existing safe flags.
- [x] No provider credential, raw diagnostic output or account identifier is
      stored or exposed.
- [x] Focused and full tests, disposable smoke checks and `git diff --check`
      pass.

## Test requirements

- Test Kimi PATH success, fixed-path fallback and missing-path failure.
- Test both Kimi and Kimi-Swarm adapters use the resolver.
- Test Gemini prompt argument shape including shell-like literal content.
- Run focused adapter/usage/routing tests and the full isolated suite.

## Constraints

- `agent_runner` remains the authority boundary.
- Preserve credential screening, minimal environments, Kimi OS confinement,
  provider usage preflight, bounded timeout, repository-integrity checks and
  no-publication worker limits.
- Do not add `--auto`, `--yolo`, permission bypass or arbitrary user flags.
- GitHub publication targets only the feature branch and later
  `projects-lifecycle-recovery`, never `main`.

## Owner decisions

None for this technical repair. Any change to the separate Kimi usage policy
requires an explicit owner decision.

## Completion report

### Implemented

- Added PATH-first Kimi executable resolution with a fixed owner-home fallback
  restricted to a non-symlink regular executable file.
- Applied the resolver to both Kimi and Kimi-Swarm adapters while keeping
  explicit executable overrides PATH-only.
- Encoded Gemini's full bounded instruction as one `--print=<prompt>` argument
  without changing its existing safety flags.
- Added regression coverage and documented the governed launch behavior.

### Files changed

- `advancore/agent_runner/worker.py`
- `tests/test_agent_runner.py`
- `tests/test_auto_pipeline.py`
- `tests/test_gemini_worker_foundation.py`
- `docs/runbooks/WORKER_ROUTING.md`
- `tasks/TASK-120-worker-cli-launch-repair.md`

### Database changes

None.

### Tests and results

- Governed auto-pipeline full suite using the project virtual environment and
  an isolated in-memory test URL: 1,227 passed.
- Focused adapter suite: 129 passed.
- `python -m py_compile` for all changed Python files and `git diff --check`:
  passed.
- Disposable no-file Kimi 0.38.0 smoke prompt: exited 0 and returned the
  expected `READY` marker.
- Disposable no-file Gemini/Antigravity 1.1.21 smoke prompt through the repaired
  adapter: exited 0 and returned the expected `READY` marker.

### Assumptions

- A symlink at the fixed Kimi path is unsafe and must fail closed even when its
  target is a regular executable.
- Provider smoke checks used a temporary empty Git repository and did not read
  or modify AdvanCore files.

### Risks / unresolved issues

- Kimi's separate 20% weekly and 60-minute local usage policy is unchanged. If
  the authenticated provider reading is already 44%, AdvanCore will still pause
  Kimi by policy even though the CLI and endpoint are healthy.

### Decisions required

- None for this technical repair. Retaining or changing the separate 20% Kimi
  usage threshold remains an owner policy decision.

### Recommended next step

Publish the reviewed repair into `projects-lifecycle-recovery`, never `main`,
then continue the separately reviewed Fleet PR #43 workflow.
