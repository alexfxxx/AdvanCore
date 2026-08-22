# TASK-010 — Controller Review Bundle Foundation

STATUS: READY

## Objective

Create a standardized, machine-readable review bundle after a worker run so an independent controller/reviewer can evaluate the result without relying on terminal screenshots or full worker transcripts.

This task improves controller handoff only. It does not grant commit, push, merge, deployment, owner, or approval authority to the runner or worker.

## Context

The current workflow already provides:

- READY-task discovery,
- fail-closed pre-run validation,
- Kimi worker execution,
- post-worker Git verification,
- local JSONL audit records,
- task lifecycle authority controls.

The remaining handoff problem is that review evidence is still scattered across terminal output, task files, Git status, test output, and local audit records.

## In scope

1. Add a review-bundle model and serializer under `advancore/agent_runner/`.
2. Produce one local review bundle after a successful worker run that reaches `AWAITING_APPROVAL`.
3. Store bundles under `.agent_runner/review/` and keep that directory gitignored via the existing `.agent_runner/` rule.
4. Use a deterministic machine-readable format such as JSON.
5. Include only safe review metadata and bounded evidence, including:
   - timestamp,
   - task ID and task filename,
   - task lifecycle status before/after when available,
   - branch,
   - pre-worker HEAD,
   - post-worker HEAD,
   - runner final status,
   - worker type and worker success,
   - post-worker verification result,
   - exact changed paths,
   - concise diff summary/statistics,
   - test result summary when reliably available,
   - audit-record reference,
   - recommended controller action: REVIEW, REWORK, or BLOCKED based only on runner evidence, never APPROVED.
6. Do not include:
   - credentials or secrets,
   - environment dumps,
   - connection strings,
   - full task body,
   - full worker transcript,
   - customer/business data,
   - arbitrary command output beyond bounded review metadata.
7. Make bundle creation explicit in CLI output:
   - `Review bundle: <path>`
   - if bundle creation fails, report the failure clearly.
8. Bundle failure must not silently disappear. It may block controller handoff if the runner cannot produce reliable review evidence.
9. Add a read-only CLI command to inspect an existing review bundle in concise form, e.g. `review-bundle show <path-or-latest>`.
10. The inspect command must not mutate repository state.
11. Add deterministic tests for bundle creation, safe-field policy, changed-path capture, serialization, inspection, and failure handling.
12. Update `docs/architecture/AGENT_RUNNER.md` and add an ADR if appropriate.
13. Run the full pytest suite.
14. Complete this task report and stop without committing or pushing.

## Recommended controller action rules

The bundle may recommend only one of:

- `REVIEW` — worker succeeded and post-worker verification passed; human/controller review is required.
- `REWORK` — worker failed but repository verification remained safe, or bounded implementation evidence is incomplete.
- `BLOCKED` — repository safety verification failed or review evidence cannot be produced reliably.

The bundle must never recommend or assert `APPROVED`.

## Out of scope

- Automatic Git staging.
- Automatic commit or push.
- Merge or branch switching.
- GitHub write actions from the runner.
- Production/deployment actions.
- Database or ERP feature work.
- Automatic controller approval.
- Automatic task transition to APPROVED.
- Remote transmission of review bundles.
- Full worker-transcript persistence.
- General orchestration redesign.

## Safety requirements

- Keep `main` non-executable.
- Existing pre/post Git safety checks remain unchanged.
- Existing lifecycle authority model remains unchanged.
- Worker cannot self-approve through review-bundle metadata.
- Owner role must not be assigned automatically.
- Bundle paths must remain repository-local under `.agent_runner/review/`.
- Review bundle generation must use trusted runner state, not worker-authored claims, wherever possible.

## Acceptance criteria

- [ ] A successful execute run produces one local review bundle.
- [ ] Bundle contains task identity, Git snapshots, runner status, worker result, verification result, changed paths, audit reference, and recommended controller action.
- [ ] Bundle never contains `APPROVED` as recommended action.
- [ ] Bundle excludes prohibited/sensitive content.
- [ ] CLI clearly prints the bundle path.
- [ ] Read-only bundle inspection works.
- [ ] Bundle-write failure is explicit and tested.
- [ ] No commit/push/merge capability is added.
- [ ] No task authority expansion is added.
- [ ] No database/model/migration changes are made.
- [ ] Full pytest suite passes.
- [ ] Architecture documentation is updated.
- [ ] Completion report is produced.

## Test requirements

At minimum test:

1. Successful worker + safe post-verification -> bundle recommends `REVIEW`.
2. Worker failure + safe Git verification -> bundle recommends `REWORK`.
3. Failed post-worker verification -> bundle recommends `BLOCKED` or bundle handoff is blocked.
4. Bundle never recommends `APPROVED`.
5. Safe metadata fields are present.
6. Sensitive/full-content fields are absent.
7. Changed paths match runner post-verification state.
8. Audit reference is present when available.
9. Bundle-write failure is reported explicitly.
10. Read-only inspection does not alter Git state.
11. Existing runner, lifecycle, and non-runner tests remain passing.

Run:

```bash
.venv/bin/python -m pytest tests/ -v
```

## Constraints

- Read and obey `AGENTS.md`.
- Stay on `agent-control-foundation`.
- Do not modify `main`.
- Do not commit or push until explicit reviewer approval.
- Keep changes small and reversible.
- Prefer standard-library JSON/path/time support over new dependencies.

## Owner decisions

None required to begin.

## Completion report

### Implemented
- Added `advancore/agent_runner/review_bundle.py` with:
  - `ControllerAction` enum (`REVIEW`, `REWORK`, `BLOCKED` — no `APPROVED`).
  - `ReviewBundle` dataclass and JSON serializer.
  - `build_review_bundle()` deriving action from runner evidence only.
  - `write_review_bundle()` / `load_review_bundle()` / `find_latest_bundle()`.
  - `format_bundle_summary()` for read-only CLI inspection.
- Integrated review-bundle creation into `execute()` in `runner.py`.
- Extended `RunnerResult` with bundle path/write status fields.
- Added `review-bundle show [<path-or-latest>]` CLI subcommand in `__main__.py`.
- Exported public review-bundle helpers in `advancore/agent_runner/__init__.py`.
- Added comprehensive tests in `tests/test_review_bundle.py`.
- Updated `docs/architecture/AGENT_RUNNER.md`.
- Added `docs/decisions/ADR-006-controller-review-bundle.md`.

### Files changed
- `advancore/agent_runner/__init__.py`
- `advancore/agent_runner/__main__.py`
- `advancore/agent_runner/runner.py`
- `advancore/agent_runner/review_bundle.py` (new)
- `docs/architecture/AGENT_RUNNER.md`
- `docs/decisions/ADR-006-controller-review-bundle.md` (new)
- `tests/test_review_bundle.py` (new)
- `tasks/TASK-010-controller-review-bundle-foundation.md` (completion report only)

### Database changes
- None. No model or migration changes.

### Tests executed and results
```bash
.venv/bin/python -m pytest tests/ -v
```
Result: **144 passed, 0 failed**.

### Assumptions
- Bundles are produced for every `execute()` run that reaches post-worker verification, not only `AWAITING_APPROVAL`, so that `REWORK` and `BLOCKED` cases are also captured as required by the test checklist.
- `.agent_runner/review/` is covered by the existing `.agent_runner/` gitignore rule; no separate gitignore edit was needed.
- Bundles intentionally do not include previous task status because the runner does not currently capture pre-run task status; `previous_status` is reserved and left null.

### Risks / unresolved issues
- Local review bundles are not signed or checksummed; tamper-evident handoff is a future extension noted in the architecture doc.
- The `review-bundle show` command relies on filesystem mtime for `latest`; clocks and filesystems must be reasonable.
- Bundle write failure is reported but does not currently change the runner's primary status; the CLI clearly marks the bundle as `NOT WRITTEN`.

### Decisions required
- None to complete this task. A controller/reviewer may later decide whether bundles should be signed, compressed, or transmitted.

### Recommended next step
- Have a controller/reviewer inspect a generated bundle with:
  ```bash
  .venv/bin/python -m advancore.agent_runner review-bundle show
  ```
- Once approved, the reviewer can commit the code changes (the bundles themselves remain gitignored).

### git status --short
