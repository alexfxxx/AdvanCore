# TASK-017 — Governed Swarm Auto-Pipeline

STATUS: READY

## Objective

Create a single-command governed development pipeline that automates the repetitive TASK execution and verification gates while preserving GitHub as source-of-truth and the AdvanCore runner as the authority enforcing governance.

The pipeline must support Kimi Swarm as the preferred implementation worker, automatically perform bounded post-worker verification, and stop with one consolidated controller-ready approval report. It must NOT stage, commit, push, merge, deploy, mutate `main`, access credentials, or make controller/lifecycle decisions.

The primary operator goal is to reduce the current multi-command manual workflow to approximately one execution command plus one owner/controller approval decision.

## Business context

TASK-005 through TASK-016 established the governed local agent runner, audit trail, post-worker verification, task lifecycle, review bundles, controller decisions, handoff/reconciliation, adapter boundary, transport envelope, and transport-driver boundary.

Those controls are now mature enough that the largest remaining operational problem is human coordination overhead. Today the owner/controller manually performs many commands for every task:

`validate → dry-run → launch Kimi → inspect review bundle → pytest → diff check → scope check → stage → verify staged files → commit → verify commit → push`

TASK-017 automates only the safe pre-publication portion:

`validate → plan → launch Kimi Swarm → review bundle → full pytest → git diff --check → exact scope validation → consolidated approval report`

The pipeline must stop before staging/commit/push. Publication remains separately gated.

## Architectural authority rule

GitHub remains source-of-truth for approved task definitions and repository history.

The local/hosted AdvanCore runner remains the authority enforcing execution policy. Kimi Swarm is an implementation worker only. Neither Kimi nor any swarm sub-agent gains controller, lifecycle, Git-publication, credential, deployment, or production authority.

## In scope

1. Add a focused orchestration module, preferably `advancore/agent_runner/auto_pipeline.py`.
2. Add a single CLI entry point such as:

   ```bash
   .venv/bin/python -m advancore.agent_runner auto TASK-018 --worker kimi-swarm
   ```

   Exact syntax may vary slightly if existing CLI conventions require it.
3. The auto pipeline must execute these gates in order and stop immediately on failure:
   - resolve and parse the approved task file;
   - verify current branch is not `main`;
   - verify branch matches task/governance expectations;
   - verify working tree is clean before worker launch;
   - verify task status is executable;
   - produce/record the canonical plan;
   - launch the selected worker;
   - capture pre/post Git snapshots;
   - generate/use the existing review bundle;
   - run the full repository pytest suite;
   - run `git diff --check` equivalent;
   - calculate the exact changed-file set;
   - compare changed files against the task's explicit allowed changed-file scope;
   - produce a consolidated controller-ready report.
4. Add explicit parsing/support for an `Allowed changed-file scope` section in governed task files. The auto pipeline must fail closed if:
   - scope is missing when auto mode requires it;
   - changed files exceed the allowed scope;
   - scope contains unsafe path escapes;
   - changed-file determination is ambiguous.
5. Preserve existing TASK-005/TASK-007/TASK-010 verification and review-bundle semantics wherever practical. Do not duplicate policy logic unnecessarily.
6. Add a bounded pipeline result model with explicit states such as:
   - `READY_FOR_APPROVAL`
   - `WORKER_FAILED`
   - `TEST_FAILED`
   - `DIFF_CHECK_FAILED`
   - `SCOPE_FAILED`
   - `VALIDATION_FAILED`
   Exact names may vary, but success/failure must be unambiguous and fail closed.
7. The success report must contain at minimum:
   - task id/title;
   - branch;
   - pre/post HEAD;
   - worker type;
   - worker success;
   - review-bundle path;
   - pytest command/result/pass count where deterministically extractable;
   - `git diff --check` result;
   - allowed changed paths;
   - actual changed paths;
   - scope-match result;
   - working-tree state;
   - explicit statement that no staging/commit/push occurred;
   - recommended next action: controller/owner review.
8. Write a bounded local pipeline artifact under an ignored location such as `.agent_runner/auto/` and include a safe audit record. Do not include full worker transcripts, secrets, environment dumps, customer data, or arbitrary repository contents.
9. Add a `KimiSwarmWorkerAdapter` or equivalent controlled worker mode.
10. Before implementing swarm invocation, inspect the installed local Kimi CLI (`kimi --help` and other safe local help output as necessary). Do not invent unsupported flags.
11. Preferred swarm behavior:
    - if the installed Kimi CLI exposes a documented non-interactive swarm capability compatible with the existing worker boundary, use that exact local capability;
    - otherwise use the existing non-interactive `kimi --prompt` boundary with a canonical instruction explicitly requiring Kimi's AgentSwarm capability for implementation/review work;
    - do not silently fall back to unrestricted `/auto`, `--yolo`, or equivalent permission-bypass modes;
    - if swarm cannot be invoked safely/non-interactively, fail explicitly and report the limitation rather than weakening governance.
12. The swarm instruction must make clear that sub-agents are implementation/review helpers only and inherit the task's exact changed-file scope and prohibited actions.
13. Swarm agents may parallelize analysis, implementation planning, testing/review, and documentation, but the pipeline must not permit uncontrolled concurrent Git publication or branch operations.
14. The worker boundary may execute only the approved Kimi process. The verification layer may execute only bounded local verification commands required by this task (pytest and read-only Git inspection/diff commands). No arbitrary user-provided shell commands.
15. Full pytest execution must use the repository's existing environment and command convention:

   ```bash
   .venv/bin/python -m pytest tests/ -v
   ```

16. `git diff --check` semantics must be enforced automatically.
17. Actual changed-file scope must include tracked modifications and untracked files created by the worker, and must not miss renamed/deleted files.
18. Auto mode must not stage files. It must not invoke `git add`, `git commit`, `git push`, `git merge`, `git reset`, `git checkout`/`switch`, rebase, tags, deployments, or destructive Git operations.
19. Auto mode must not transition the task to an approved/published lifecycle state by itself.
20. Auto mode must not create or fabricate a controller decision. A passing auto pipeline means `READY_FOR_APPROVAL`, never `APPROVED`.
21. Add deterministic tests covering successful pipeline execution with mocked/fake workers, worker failure, pytest failure, diff-check failure, scope mismatch, untracked-file detection, deleted/renamed-file scope handling, dirty-tree rejection, main-branch rejection, task-scope parsing, safe report/audit generation, and absence of staging/commit/push side effects.
22. Add deterministic tests for `KimiSwarmWorkerAdapter` command/instruction construction without requiring live Kimi network/model execution in the automated test suite.
23. Update `docs/architecture/AGENT_RUNNER.md` and add `docs/decisions/ADR-017-governed-swarm-auto-pipeline.md`.
24. Run the full pytest suite.
25. Complete this task-file Completion report and stop without staging, committing, or pushing.

## Important governance rule

Automation removes repetitive operator commands; it does not remove authority boundaries.

A successful auto run means only:

`IMPLEMENTATION + VERIFICATION COMPLETE → READY FOR CONTROLLER/OWNER REVIEW`

It must never mean:

`APPROVED`, `COMMITTED`, `PUSHED`, `MERGED`, or `DEPLOYED`.

## Kimi Swarm governance

Kimi Swarm is authorized only as a bounded implementation worker under the AdvanCore runner.

Every swarm/sub-agent must inherit these restrictions:

- read approved repository files as needed;
- modify only paths authorized by the task's allowed changed-file scope;
- run local tests/inspection necessary for implementation;
- do not commit;
- do not push;
- do not merge;
- do not switch branches;
- do not access credentials or secrets;
- do not alter production databases;
- do not deploy;
- do not change commercial/compliance policy;
- do not declare its own work approved;
- stop with a completion report and Git status.

The AdvanCore runner, not Kimi Swarm, determines whether the resulting work passes governance.

## Explicitly out of scope

- Automatic staging.
- Automatic commit.
- Automatic push.
- Automatic merge to `main`.
- Automatic deployment.
- Automatic controller approval.
- Automatic lifecycle approval/apply.
- Autonomous production database changes.
- Credential/API-key/token storage or access.
- Remote HTTP/webhook/controller transport.
- Kimi Claw integration.
- Long-running daemons/background schedulers.
- Automatic task generation from natural-language goals (planned for a later task).
- Automatic iterative repair loops after failed verification (planned for a later task).
- OpenAI/ChatGPT API integration as controller.

## Allowed changed-file scope

The worker may change only these eight paths unless it stops and reports why an additional path is required:

1. `advancore/agent_runner/auto_pipeline.py` (new)
2. `advancore/agent_runner/worker.py`
3. `advancore/agent_runner/__init__.py`
4. `advancore/agent_runner/__main__.py`
5. `tests/test_auto_pipeline.py` (new)
6. `docs/architecture/AGENT_RUNNER.md`
7. `docs/decisions/ADR-017-governed-swarm-auto-pipeline.md` (new)
8. `tasks/TASK-017-governed-swarm-auto-pipeline.md`

No other file is authorized for modification in TASK-017. If implementation genuinely requires another file, stop before changing it and report the need for reviewer approval.

## Database impact

None. No schema, model, migration, or production database change is authorized.

## Safety requirements

- Read and obey `AGENTS.md`.
- Stay on `agent-control-foundation`.
- `main` remains untouched and non-executable.
- GitHub remains source-of-truth.
- The AdvanCore runner remains policy authority.
- Kimi/Kimi Swarm remains worker only.
- Reuse existing task validation, runner, review bundle, audit, Git snapshot, and controller-governance helpers wherever practical.
- Unknown, stale, malformed, conflicting, mismatched, unauthorized, ambiguous, or unsafe evidence fails closed.
- Keep implementation standard-library-first and dependency-free unless an existing dependency is already available.
- Do not weaken existing fail-closed behavior to make auto mode easier.

## Acceptance criteria

- [ ] One-command `auto` pipeline exists.
- [ ] Auto pipeline performs validation, worker execution, review-bundle generation, full pytest, diff check, and exact scope verification automatically.
- [ ] Pipeline stops at `READY_FOR_APPROVAL` on success.
- [ ] Pipeline stops immediately and clearly on any failed gate.
- [ ] No staging/commit/push/merge/deployment occurs.
- [ ] Explicit allowed changed-file scope is parsed and enforced.
- [ ] Untracked, deleted, and renamed files are included in scope validation.
- [ ] Dirty initial working tree is rejected.
- [ ] `main` is rejected.
- [ ] Kimi Swarm worker mode exists and uses only locally supported safe invocation behavior.
- [ ] No unsupported Kimi swarm flags are invented.
- [ ] No unrestricted `/auto`, `--yolo`, or equivalent permission-bypass mode is introduced.
- [ ] Swarm sub-agents inherit the task scope and governance restrictions.
- [ ] Kimi Swarm has no controller/publication authority.
- [ ] Full pytest result is captured in the consolidated report.
- [ ] `git diff --check` result is captured in the consolidated report.
- [ ] Review-bundle path is captured in the consolidated report.
- [ ] Actual vs allowed changed paths are captured in the consolidated report.
- [ ] Safe local auto-run artifact/audit record exists.
- [ ] Full worker transcript/secrets/environment dumps/customer data are not persisted in auto artifacts.
- [ ] Existing TASK-005 through TASK-016 governance semantics remain intact.
- [ ] Existing tests remain passing.
- [ ] Full pytest suite passes.
- [ ] Architecture documentation and ADR are updated.
- [ ] Exact eight-file changed scope is respected.
- [ ] Completion report is written into this task file.

## Test requirements

At minimum test:

1. Clean feature branch + READY task + successful fake worker + passing tests/diff/scope → `READY_FOR_APPROVAL`.
2. Initial dirty tree → rejected before worker launch.
3. `main` branch → rejected before worker launch.
4. Non-executable task status → rejected.
5. Missing allowed changed-file scope → rejected in auto mode.
6. Unsafe scope path (`../`, absolute path, repository escape) → rejected.
7. Worker failure → pipeline stops; pytest/publication not performed.
8. Pytest failure → `TEST_FAILED`; no staging/commit/push.
9. `git diff --check` failure → `DIFF_CHECK_FAILED`.
10. Actual tracked modification outside scope → `SCOPE_FAILED`.
11. Untracked file outside scope → `SCOPE_FAILED`.
12. Allowed untracked file → accepted for scope purposes.
13. Deleted file detection participates in scope validation.
14. Renamed file detection participates in scope validation using both old/new paths as appropriate.
15. Existing review bundle is generated/referenced consistently.
16. Pre/post HEAD evidence is captured and unexpected worker commit/HEAD movement fails closed.
17. Worker-created staging/index changes are detected and fail closed or are reported as a governance failure without altering the index.
18. Consolidated report excludes full task body, worker transcript, secrets, environment dumps, and arbitrary repository content.
19. Auto artifact write failure is explicit/fail-closed.
20. Audit write failure is explicit/fail-closed where audit is required.
21. `KimiSwarmWorkerAdapter` uses documented local Kimi CLI capability when represented by test fixtures.
22. Swarm adapter fallback instruction explicitly requests AgentSwarm and includes scope/prohibited-action governance.
23. Swarm adapter never adds unrestricted permission-bypass flags.
24. No automatic controller decision, lifecycle apply, staging, commit, push, merge, branch switch, deployment, or production DB mutation occurs.
25. Existing TASK-005 through TASK-016 tests and non-runner tests remain passing.

Run:

```bash
.venv/bin/python -m pytest tests/ -v
```

## Constraints

- Inspect `worker.py`, `runner.py`, `validation.py`, `task.py`, `review_bundle.py`, `audit.py`, `git_info.py`, TASK-007, TASK-010, TASK-015, and TASK-016 before coding.
- Inspect local `kimi --help` before deciding swarm invocation syntax.
- Do not modify `main`.
- Do not commit or push until explicit reviewer approval.
- Do not add real network/controller transport in this task.
- Do not add Claw integration in this task.
- Do not add automatic repair loops yet.
- Do not add natural-language goal → task generation yet.
- Do not expand beyond the exact eight-file scope without stopping for reviewer approval.

## Owner decisions

Approved for this task:

- GitHub remains source-of-truth.
- Local/hosted AdvanCore runner remains governance authority.
- Kimi Swarm is the preferred implementation worker when safely supported by the installed Kimi tooling.
- Automation may run bounded implementation verification automatically.
- Staging, commit, push, merge, deployment, controller approval, and lifecycle approval remain gated.

No further owner decision is required to begin TASK-017.

## Completion report

To be completed by the worker. Report:

- Implemented
- Kimi swarm invocation method selected and why
- Files changed
- Database changes
- Tests executed and results
- Auto-pipeline verification results
- Assumptions
- Risks / unresolved issues
- Decisions required
- Recommended next step
- `git status --short`
