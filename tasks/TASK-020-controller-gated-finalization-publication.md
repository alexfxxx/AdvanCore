# TASK-020 — Controller-Gated Finalization + Branch Publication

STATUS: READY

## Objective

Remove the remaining repetitive post-build courier steps by adding one governed finalization path that can consume a valid controller approval decision for a successfully verified auto-pipeline result, apply only the already-authorized lifecycle transitions, stage exactly the verified task scope, create one local commit, and push only the current non-`main` feature branch.

This task must preserve the existing authority model. Publication is allowed only after independently valid controller authority is present and all verification evidence still matches the current repository state. The runner must never infer approval from test success, Kimi output, review-bundle state, file presence, or transport success.

The goal is to replace the current manual sequence:

`worker lifecycle transitions → controller approval transition → git add exact files → staged verification → commit → clean-tree verification → commit-content verification → push → post-push status`

with one bounded controller-gated finalization command.

## Business context

TASK-017 automated implementation verification. TASK-018 added bounded autonomous repair. TASK-019 added owner-goal → governed DRAFT task generation. The largest remaining repetitive owner burden is now publication choreography after a clean `READY_FOR_APPROVAL` result.

The long-term target remains:

`Owner goal → governed task → worker/swarm → verification/repair → controller review → owner sees only meaningful exceptions/approval requests`

TASK-020 is the safe publication bridge needed before any remote controller integration. It must not merge to `main` or deploy.

## Governance model

- **Worker/swarm** remains implementation authority only.
- **Worker lifecycle authority** remains limited to `READY → IN_PROGRESS`, `REWORK → IN_PROGRESS`, and `IN_PROGRESS → REVIEW`.
- **Controller/reviewer** remains the only non-owner authority allowed to approve `REVIEW → APPROVED`.
- **Runner** may orchestrate those existing transitions on behalf of the correct recorded actor, but may not invent or broaden authority.
- **Git publication** may occur only after a separately valid controller approval decision and matching verified evidence.
- **GitHub** remains source-of-truth.
- **`main` remains untouched**.

## In scope

1. Add a focused module, preferably `advancore/agent_runner/finalize.py`.
2. Define bounded result/status models for finalization, including states equivalent to:
   - `READY_TO_FINALIZE`;
   - `FINALIZED_LOCAL`;
   - `PUSHED`;
   - `BLOCKED` / `STALE_EVIDENCE` / `DECISION_REJECTED` / `PUBLICATION_FAILED`.
3. Consume existing TASK-010 through TASK-018 artifacts rather than inventing parallel authority models. Reuse where practical:
   - review bundle;
   - controller handoff/decision/reconciliation;
   - lifecycle transition helpers;
   - auto-pipeline artifact/result evidence;
   - Git info helpers.
4. Require a separately valid controller decision record that resolves to `APPROVE` through existing validation/reconciliation logic before any lifecycle approval, staging, commit, or push occurs.
5. Never accept Kimi/worker-authored approval. Existing controller actor restrictions remain authoritative.
6. Validate that finalization evidence is fresh and matches current repository state. At minimum bind:
   - task id;
   - branch;
   - pre/post HEAD as applicable;
   - review bundle identity/path;
   - verified changed-file set;
   - no staged paths at start;
   - current working-tree paths exactly matching the verified scope/result;
   - current branch remains non-`main` and is the same branch verified by the auto-pipeline.
7. Fail closed if evidence is missing, stale, ambiguous, mismatched, malformed, or points to a different task/branch/HEAD/change set.
8. Automate existing worker lifecycle choreography where safe:
   - if a successfully implemented executable task is still `READY`, apply `READY → IN_PROGRESS` attributed/audited as `worker`;
   - then apply `IN_PROGRESS → REVIEW` attributed/audited as `worker`;
   - do not skip lifecycle states;
   - do not synthesize these transitions when repository/verification evidence is not clean and matching.
9. Apply `REVIEW → APPROVED` only after the valid controller approval decision is reconciled. This transition must be attributed/audited as `controller`.
10. A controller `REWORK`, `REJECT`, `BLOCKED`, missing decision, or invalid decision must never stage/commit/push.
11. Stage only the exact verified changed-file set. Do not use `git add .`, `git add -A`, wildcard staging, or repository-wide staging.
12. After staging, independently verify the staged name/status set exactly matches the authorized verified paths. Any mismatch must stop before commit.
13. Run `git diff --cached --check` before commit and fail closed on error.
14. Use a deterministic bounded commit-message policy, e.g. task-derived `agent: <normalized task title>`, or accept an optional controller-supplied bounded commit message. Do not allow shell interpolation or arbitrary command execution.
15. Create exactly one local commit for the approved task.
16. After commit, verify:
   - working tree clean;
   - commit contains exactly the approved paths;
   - branch unchanged;
   - commit parent is the expected pre-commit HEAD;
   - no merge commit was created.
17. Push only the current verified feature branch to its configured `origin/<same-branch>` ref.
18. Explicitly reject push when current branch is `main`, target branch is `main`, branch changed since verification, upstream points to an unexpected branch, or a force push would be required.
19. Use normal fast-forward `git push origin <current-branch>` semantics only. Never use force, force-with-lease, refspec rewriting, tags, delete, or branch creation.
20. After push, verify local branch is synchronized with `origin/<same-branch>` and the working tree is clean.
21. Record a bounded finalization artifact/audit trail under ignored `.agent_runner/` paths containing safe metadata only: task id, decision reference, branch, pre/post commit HEAD, changed/staged paths, commit SHA, push result, lifecycle states, and terminal status.
22. Never record secrets, credentials, environment dumps, full worker transcripts, arbitrary source contents, customer data, or unrestricted command output.
23. Add one CLI command such as:
   - `finalize TASK-020 --decision <path-or-latest>`
   - with default preview/dry-run behavior;
   - and an explicit `--apply` for lifecycle/stage/commit/push mutation.
24. Preview mode must perform all safe validation it can and show exactly what would happen without changing lifecycle, index, HEAD, or remote.
25. Apply mode must stop at the first failed gate and report the exact blocking condition.
26. Do not automatically merge to `main`, open/deploy releases, alter production systems, or mutate production databases.
27. Do not add remote ChatGPT/OpenAI API integration, Claw integration, background daemons, or webhook behavior in this task.
28. Add deterministic tests for authority binding, stale evidence, lifecycle choreography, exact staging, commit integrity, push restrictions, no-force behavior, fail-closed publication, and preview safety.
29. Update `docs/architecture/AGENT_RUNNER.md` and add `docs/decisions/ADR-020-controller-gated-finalization-publication.md`.
30. Run the full pytest suite.
31. Complete this task-file Completion report and stop without self-finalizing TASK-020. TASK-020 itself must still be reviewed and published through the pre-existing governed process because it is implementing the new finalizer.

## Important governance rule

**Verification is evidence. Controller approval is authority. Finalization executes authority; it does not create it.**

The finalizer must never:

- infer `APPROVE` from passing tests or `READY_FOR_APPROVAL`;
- accept worker/swarm/Kimi approval;
- bypass controller-decision validation or handoff reconciliation;
- skip lifecycle states;
- stage files outside the verified path set;
- commit when staged scope differs from verified scope;
- push `main`;
- force push;
- merge;
- deploy;
- access secrets or credentials beyond normal already-configured local Git authentication;
- modify Git remotes or credential configuration;
- continue after stale/mismatched/ambiguous evidence.

## Explicitly out of scope

- Merge to `main`.
- Pull request auto-merge.
- Production deployment.
- Release/tag publication.
- Force push or history rewrite.
- Remote controller API integration.
- OpenAI/ChatGPT API integration.
- Kimi/Claw as controller authority.
- Claw integration.
- Background services/webhooks/polling.
- Secret/token/key management.
- Database/model/migration changes for TASK-020 itself.
- Automatic owner business/policy decisions.
- Automatic controller-decision creation.

## Allowed changed-file scope

The TASK-020 implementation worker may change only these eight paths unless it stops and reports why another path is required:

1. `advancore/agent_runner/finalize.py` (new)
2. `advancore/agent_runner/__init__.py`
3. `advancore/agent_runner/__main__.py`
4. `tests/test_finalize.py` (new)
5. `docs/architecture/AGENT_RUNNER.md`
6. `docs/decisions/ADR-020-controller-gated-finalization-publication.md` (new)
7. `tasks/TASK-020-controller-gated-finalization-publication.md`
8. `advancore/agent_runner/audit.py` only if bounded finalization audit metadata cannot be expressed through existing generic audit helpers.

No other file is authorized for TASK-020. If implementation genuinely requires another path, stop before changing it and report the need for controller approval.

## Database impact

None. No schema, model, migration, production database, or business-data mutation is authorized.

## Safety requirements

- Read and obey `AGENTS.md`.
- Stay on `agent-control-foundation`.
- GitHub remains source-of-truth.
- `main` remains untouched and non-executable.
- Preserve TASK-009 lifecycle authority exactly.
- Preserve TASK-010 through TASK-016 controller/transport authority exactly.
- Preserve TASK-017/TASK-018 auto/repair verification semantics.
- Preserve TASK-019 goal-to-task semantics.
- Reuse existing validation/reconciliation helpers rather than duplicating authority checks.
- Fail closed on stale, malformed, ambiguous, mismatched, unauthorized, or unsafe state.
- Standard-library-first; no new dependency unless already approved.

## Acceptance criteria

- [ ] Controller-gated finalization module exists.
- [ ] Preview mode mutates nothing.
- [ ] Apply mode requires a separately valid controller `APPROVE` decision.
- [ ] Worker-authored/invalid/missing decisions cannot finalize.
- [ ] Verified review/auto evidence is bound to current task/branch/HEAD/change set.
- [ ] Stale or mismatched evidence fails closed.
- [ ] Worker lifecycle transitions are orchestrated only under existing actor authority.
- [ ] Controller lifecycle approval occurs only after controller decision reconciliation.
- [ ] Staging uses exact explicit verified paths only.
- [ ] Staged scope is independently reverified before commit.
- [ ] Cached diff check passes before commit.
- [ ] Exactly one non-merge commit is created.
- [ ] Commit contents exactly match approved paths.
- [ ] Working tree is clean after commit.
- [ ] Push targets only `origin/<current-feature-branch>`.
- [ ] `main` push is impossible through this command.
- [ ] Force push/history rewrite is impossible through this command.
- [ ] Post-push branch/upstream synchronization is verified.
- [ ] No merge/deploy/tag/release behavior exists.
- [ ] Finalization audit/artifact contains bounded safe metadata only.
- [ ] Exact TASK-020 changed-file scope is respected.
- [ ] Existing tests remain passing.
- [ ] Full pytest suite passes.
- [ ] Architecture docs and ADR updated.
- [ ] Completion report written into task file.

## Test requirements

At minimum test:

1. Preview with valid evidence/decision reports intended actions and changes nothing.
2. Missing decision blocks all mutation.
3. Worker-authored approval blocks all mutation.
4. Controller REWORK/REJECT/BLOCKED blocks publication.
5. Valid controller APPROVE + matching evidence allows finalization path.
6. Task mismatch blocks.
7. Branch mismatch blocks.
8. HEAD/evidence mismatch blocks.
9. Changed-path mismatch blocks.
10. Existing staged paths at start block.
11. `main` branch blocks.
12. Lifecycle READY → IN_PROGRESS is applied as worker only when warranted.
13. IN_PROGRESS → REVIEW is applied as worker only when warranted.
14. REVIEW → APPROVED occurs only after valid controller approval decision.
15. No lifecycle state is skipped.
16. Exact explicit `git add <paths...>` behavior; no `git add .`/`-A`/wildcard.
17. Staged path mismatch stops before commit.
18. `git diff --cached --check` failure stops before commit.
19. Commit message is bounded/safe.
20. Exactly one commit created and parent relationship verified.
21. Commit changed paths exactly match approved set.
22. Post-commit dirty tree blocks push.
23. Push command is exactly normal origin/current-branch semantics.
24. Push to `main` impossible.
25. Force-push flags are never used.
26. Remote/upstream mismatch fails closed.
27. Successful push ends synchronized and clean.
28. Publication failure reports bounded evidence without hiding local commit state.
29. Audit/artifact metadata is bounded and excludes transcripts/secrets.
30. Existing TASK-009 through TASK-019 tests remain passing.

Run:

```bash
.venv/bin/python -m pytest tests/ -v
```

## Constraints

- Do not redesign controller authority.
- Do not add automatic controller-decision creation.
- Do not add merge/deploy/main publication.
- Do not broaden beyond exact allowed changed-file scope without stopping.
- Do not self-finalize TASK-020 using the feature being implemented.

## Owner decisions

The owner has already established the project objective of minimizing repetitive courier work while preserving explicit authority boundaries. TASK-020 is therefore authorized to implement controller-gated staging/commit/push **only for the current verified non-`main` feature branch and only after a separately valid controller APPROVE decision**.

Any future merge-to-main, deployment, release publication, or controller-decision automation remains separately gated.

## Completion report

To be completed by the worker. Report:

- Implemented
- Files changed
- Database changes
- Tests executed and results
- Assumptions
- Risks / unresolved issues
- Decisions required
- Recommended next step
- `git status --short`
