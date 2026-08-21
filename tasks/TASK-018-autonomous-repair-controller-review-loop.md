# TASK-018 — Autonomous Repair + Controller Review Loop

STATUS: READY

## Objective

Extend the TASK-017 governed auto-pipeline with a bounded autonomous repair loop so recoverable worker/test/diff/scope failures can be sent back to the selected Kimi worker (preferably `kimi-swarm`) with exact failure evidence, re-verified automatically, and escalated to controller/owner review only when the bounded repair budget is exhausted or the failure is unsafe/non-repairable.

This task must preserve GitHub as source-of-truth and the local/hosted AdvanCore runner as the governance authority. It must NOT add automatic staging, commit, push, merge, deployment, credential access, production database mutation, or controller approval.

## Business context

TASK-017 reduced the manual workflow to one governed auto-pipeline command:

`validate → worker → review bundle → full pytest → diff-check → exact scope verification → approval report`

The next largest source of owner time is recoverable failure handling. Today, a failed test or review gate still requires a human to inspect the failure and manually re-run Kimi. TASK-018 should automate that repair cycle while keeping the same governance perimeter.

Target flow:

`Goal/Task → governed auto-pipeline → PASS → READY_FOR_APPROVAL`

or

`Goal/Task → governed auto-pipeline → repairable FAIL → bounded repair prompt → Kimi/Kimi-Swarm → re-run all gates → PASS or retry → escalate`

The repair loop is implementation assistance only. It never grants controller authority and never publishes code.

## In scope

1. Extend `advancore/agent_runner/auto_pipeline.py` with a bounded repair orchestration layer.
2. Add explicit repair configuration/result models, including at minimum:
   - maximum repair attempts;
   - current attempt number;
   - triggering gate/status;
   - bounded failure evidence;
   - worker type used for repair;
   - per-attempt verification result;
   - terminal outcome such as `READY_FOR_APPROVAL`, `REPAIR_EXHAUSTED`, `NON_REPAIRABLE`, or equivalent fail-closed states.
3. Default repair budget must be small and deterministic (recommended maximum 2 repair attempts unless an even safer limit is justified).
4. Repair may be attempted only for explicitly classified recoverable failures, at minimum considering:
   - worker implementation failure where safe bounded evidence exists;
   - pytest failure;
   - `git diff --check` failure;
   - changed-file scope failure only when the out-of-scope changes can be safely reverted/removed by the worker without destructive Git operations.
5. Non-repairable conditions must fail closed and escalate immediately, including at minimum:
   - branch/HEAD mutation;
   - staged changes detected;
   - missing or unsafe allowed scope;
   - task lifecycle/authority violation;
   - credentials/secrets request;
   - production/database/deployment request;
   - destructive Git operation requirement;
   - ambiguous repository state;
   - audit/artifact integrity failure where safe continuation cannot be proven.
6. Build a bounded canonical repair instruction that contains only the evidence needed to fix the current task. It must not dump arbitrary repository content, secrets, environment variables, full transcripts, customer data, or unrestricted command output.
7. Repair instructions must restate the task allowed changed-file scope and prohibited actions for every attempt.
8. Prefer `kimi-swarm` for repair when the original worker is `kimi-swarm`; otherwise preserve the selected worker unless a safer deterministic policy is defined.
9. A repair attempt must never use unrestricted `/auto`, `--yolo`, permission-bypass, or equivalent modes.
10. After every repair attempt, rerun the full governed verification sequence, not only the previously failing gate:
    - post-worker Git/branch/HEAD checks;
    - full pytest suite;
    - `git diff --check` (unstaged and staged checks consistent with TASK-017);
    - exact changed-file scope verification;
    - staged-path detection;
    - review/auto artifacts and audit where applicable.
11. A successful repair must result only in `READY_FOR_APPROVAL` (or existing equivalent). It must NOT transition lifecycle to APPROVED, stage files, commit, push, merge, or deploy.
12. A failed repair must preserve evidence and either retry within budget or stop with a consolidated escalation report.
13. Add CLI support to the existing `auto` command with a bounded option such as:
    - `--repair-attempts N`
    Exact naming may vary if a smaller compatible interface is clearer.
14. Default behavior without the repair option should remain backward-compatible and safe.
15. The CLI must print one consolidated final report showing:
    - task id;
    - worker;
    - repair attempts used;
    - terminal status;
    - pytest result/count;
    - diff-check result;
    - scope result;
    - staged paths;
    - review/auto artifact paths;
    - whether owner/controller action is required.
16. Add safe audit/auto-artifact metadata for repair attempts. Include bounded identifiers/statuses only; do not add full worker transcripts or arbitrary command output.
17. Add deterministic tests for repair classification, bounded retry behavior, evidence construction, scope preservation, fail-closed escalation, no-publication guarantees, and CLI behavior.
18. Update `docs/architecture/AGENT_RUNNER.md` and add `docs/decisions/ADR-018-autonomous-repair-controller-review-loop.md`.
19. Run the full pytest suite.
20. Complete this task-file Completion report and stop without staging, committing, or pushing.

## Important governance rule

Autonomous repair is bounded implementation assistance, not authority.

It must never:

- make Kimi or any swarm/sub-agent the controller;
- infer or fabricate approval;
- change lifecycle to `APPROVED`;
- stage, commit, push, merge, tag, deploy, switch branches, rebase, reset, or rewrite history;
- access credentials, secrets, tokens, production data, or production databases;
- expand changed-file scope without explicit reviewer approval;
- hide or delete audit evidence;
- continue after a non-repairable governance failure.

## Explicitly out of scope

- Automatic commit/push/merge/publication.
- Automatic `main` changes.
- Deployment.
- Production database/model/migration changes unless explicitly part of a later approved feature task.
- Secret/token/key handling.
- Remote controller/API integration.
- Claw integration.
- Goal-to-task generation (reserved for TASK-019).
- Unlimited/self-directed repair loops.
- Background daemons or continuous polling.
- Unrestricted Kimi auto/yolo modes.

## Allowed changed-file scope

The worker may change only these eight paths unless it stops and reports why an additional path is required:

1. `advancore/agent_runner/auto_pipeline.py`
2. `advancore/agent_runner/worker.py`
3. `advancore/agent_runner/__init__.py`
4. `advancore/agent_runner/__main__.py`
5. `tests/test_auto_pipeline.py`
6. `docs/architecture/AGENT_RUNNER.md`
7. `docs/decisions/ADR-018-autonomous-repair-controller-review-loop.md` (new)
8. `tasks/TASK-018-autonomous-repair-controller-review-loop.md`

No other file is authorized for modification in TASK-018. If implementation genuinely requires another file, stop before changing it and report the need for reviewer approval.

## Database impact

None. No schema, model, migration, or production database change is authorized.

## Safety requirements

- Read and obey `AGENTS.md`.
- Stay on `agent-control-foundation`.
- `main` remains untouched and non-executable.
- Reuse TASK-017 auto-pipeline validation and verification helpers rather than duplicating them.
- Preserve TASK-009 lifecycle authority rules.
- Preserve TASK-010 through TASK-016 controller/transport authority boundaries.
- Unknown, malformed, stale, unsafe, conflicting, ambiguous, or unauthorized evidence fails closed.
- Keep changes small, reversible, standard-library-first, and dependency-free unless already available.
- GitHub remains source-of-truth; the AdvanCore runner remains the enforcement boundary.

## Acceptance criteria

- [ ] Bounded repair-loop orchestration exists.
- [ ] Repair attempt budget is explicit and deterministic.
- [ ] Recoverable vs non-repairable failures are explicitly classified and tested.
- [ ] Repair prompt contains bounded evidence only.
- [ ] Allowed changed-file scope is restated in every repair attempt.
- [ ] Full verification reruns after every repair attempt.
- [ ] Successful repair ends at `READY_FOR_APPROVAL` only.
- [ ] Exhausted repair budget produces a consolidated escalation result.
- [ ] Non-repairable governance failures stop immediately.
- [ ] Branch/HEAD/staging/publication violations fail closed.
- [ ] No automatic staging/commit/push/merge/deploy exists.
- [ ] No credential/secret/production access exists.
- [ ] No unrestricted auto/yolo mode exists.
- [ ] Default TASK-017 auto behavior remains compatible when repair is not requested.
- [ ] CLI supports a bounded repair-attempt option.
- [ ] Audit/auto artifact records repair attempts with bounded safe metadata.
- [ ] Exact eight-file changed scope is respected.
- [ ] Existing tests remain passing.
- [ ] Full pytest suite passes.
- [ ] Architecture documentation and ADR are updated.
- [ ] Completion report is written into this task file.

## Test requirements

At minimum test:

1. Repair disabled/default preserves TASK-017 behavior.
2. Pytest failure classified as repairable and triggers one repair attempt.
3. Diff-check failure classified as repairable and triggers bounded repair.
4. Worker failure with bounded evidence is repairable when safe.
5. Missing/unsafe scope is non-repairable and does not launch repair.
6. Staged paths detected → non-repairable escalation.
7. Branch or HEAD mutation → non-repairable escalation.
8. Out-of-scope changes do not get silently accepted.
9. Repair instruction includes task id/path, attempt number, failing gate, bounded evidence, and exact allowed scope.
10. Repair instruction excludes full transcripts, secrets, environment dumps, and arbitrary repository content.
11. Repair attempt uses selected safe worker and never unrestricted auto/yolo modes.
12. Full pytest reruns after repair.
13. Diff-check reruns after repair.
14. Exact scope verification reruns after repair.
15. First repair succeeds → terminal `READY_FOR_APPROVAL`.
16. First repair fails, second succeeds → terminal `READY_FOR_APPROVAL` with two attempts recorded.
17. Repair budget exhausted → terminal `REPAIR_EXHAUSTED` (or equivalent) and owner/controller action required.
18. Non-repairable failure stops without consuming remaining repair budget.
19. Audit/auto artifact contains bounded per-attempt metadata.
20. No stage/commit/push/merge/lifecycle-approval action occurs during repair.
21. CLI consolidated output reports attempts and terminal status.
22. Existing TASK-017 and earlier runner tests remain passing.

Run:

```bash
.venv/bin/python -m pytest tests/ -v
```

## Constraints

- Inspect TASK-017 `auto_pipeline.py`, `worker.py`, CLI wiring, audit behavior, and tests before coding.
- Do not modify `main`.
- Do not commit or push until explicit reviewer approval.
- Do not introduce real remote controller transport, Claw integration, credentials, background services, or publication automation.
- Do not broaden worker authority or lifecycle authority.
- Do not expand beyond the exact eight-file scope without stopping for reviewer approval.

## Owner decisions

None required to begin.

The default maximum repair-attempt count may be chosen by implementation if it is bounded to 1–2 attempts and documented. A value above 2 requires owner approval.

## Completion report

To be completed by the worker. Report:

- Implemented
- Files changed
- Database changes
- Tests executed and results
- Repair policy chosen
- Assumptions
- Risks / unresolved issues
- Decisions required
- Recommended next step
- `git status --short`
