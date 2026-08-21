# TASK-012 — Controller Decision Lifecycle Bridge

STATUS: READY

## Objective

Connect a validated controller decision record from TASK-011 to the existing authority-aware task lifecycle from TASK-009 through a bounded, fail-closed bridge.

The bridge must let an independent controller/reviewer explicitly preview and, only with a separate apply flag, request the corresponding lifecycle transition for the linked task. It must not grant the worker approval authority and must not stage, commit, push, merge, deploy, or switch branches.

## Business context

The current local control-plane flow is now:

`GitHub Task → Local Agent Runner → Kimi worker → post-worker verification → audit → review bundle → controller decision record`

TASK-011 created the return-path decision artifact, but that artifact is intentionally passive: recording `APPROVE`, `REWORK`, or `BLOCKED` does not change task lifecycle state.

The remaining gap is a controlled bridge from that decision record into the existing lifecycle state machine. The bridge must reuse the established authority model rather than inventing a second approval system.

## Facts

- TASK-009 provides `TaskStatus`, `ActorRole`, `is_transition_allowed()`, and `transition_task()`.
- TASK-010 provides local review bundles under `.agent_runner/review/`.
- TASK-011 provides local controller decision records under `.agent_runner/decisions/`.
- Controller decision values are exactly `APPROVE`, `REWORK`, or `BLOCKED`.
- `APPROVE` is currently only a decision-record value; it performs no task transition.
- Lifecycle transition authority already prevents worker self-approval.
- Commit, push, merge, deployment, destructive operations, secrets access, and commercial/compliance changes remain separately gated.

## In scope

1. Add a small decision-to-lifecycle bridge under `advancore/agent_runner/` or extend the existing lifecycle/controller-decision modules in a narrowly scoped way.
2. Map controller decision values to requested lifecycle targets:
   - `APPROVE` → `APPROVED`
   - `REWORK` → `REWORK`
   - `BLOCKED` → `BLOCKED`
3. Reuse the existing TASK-009 lifecycle transition matrix and actor-role authority. Do not create a parallel transition-authority model.
4. Add a CLI command with preview-only default behavior, for example:
   - `controller-decision apply <decision-or-latest>`
   - default: preview only;
   - explicit `--apply` required to mutate the task file.
5. Before any lifecycle mutation, validate the decision record and its linkage to trusted local evidence, including:
   - decision record exists and parses correctly,
   - actor role is `controller` or `owner`, never `worker`,
   - decision value is known,
   - linked review-bundle reference exists and parses correctly,
   - decision task ID/filename matches the linked review bundle,
   - linked review bundle branch matches the current branch,
   - task file exists and identity matches the decision/bundle,
   - lifecycle transition is valid for the task's current status and decision actor.
6. Fail closed on missing, malformed, inconsistent, stale, or ambiguous linkage evidence.
7. For `APPROVE`, require lifecycle conditions that already permit `REVIEW → APPROVED`; do not bypass the existing state machine merely because a decision record says `APPROVE`.
8. For `REWORK`, require a lifecycle path already permitted by TASK-009; do not invent a direct transition from an otherwise invalid state.
9. For `BLOCKED`, reuse the existing non-final-state rules from TASK-009.
10. Preview output must clearly report:
    - task identity,
    - current lifecycle status,
    - controller decision,
    - actor role,
    - mapped target status,
    - whether the transition is permitted,
    - whether mutation was applied,
    - decision-record path,
    - linked review-bundle path,
    - audit result/reference when available.
11. `--apply` may mutate only the linked task file's `STATUS:` line through the existing lifecycle helper. No other repository file may be changed by the bridge itself.
12. Add local audit metadata for bridge preview/apply attempts, preferably by reusing the existing lifecycle audit path or a small compatible extension.
13. Add deterministic tests for mapping, preview behavior, explicit apply behavior, authority restrictions, linkage validation, stale/mismatched evidence, invalid lifecycle states, audit behavior, and no-Git-publication side effects.
14. Update `docs/architecture/AGENT_RUNNER.md` and add an ADR if the implementation introduces a material architectural decision.
15. Run the full pytest suite.
16. Complete the task-file Completion report and stop without committing or pushing.

## Important lifecycle rule

A controller decision record is evidence of a controller decision; it is not permission to bypass lifecycle state.

Examples:

- A valid `APPROVE` decision against a task currently in `REVIEW` may preview/apply `REVIEW → APPROVED` when the actor is authorized.
- The same `APPROVE` decision against a task still in `READY`, `IN_PROGRESS`, or `REWORK` must fail closed rather than jumping directly to `APPROVED`.
- A `REWORK` or `BLOCKED` decision must likewise obey the existing TASK-009 transition matrix.

## Evidence freshness / linkage requirements

The bridge must validate enough repository-local evidence to prevent applying a decision to the wrong task or branch.

At minimum:

- current branch must equal the branch captured in the linked review bundle;
- decision and bundle task identity must agree;
- linked task file identity must agree;
- worker actor must be rejected;
- malformed or missing linked artifacts must fail closed.

Do not require current HEAD to equal the bundle's pre/post HEAD if doing so would make an otherwise valid post-review human commit impossible without a separately approved policy. Instead, treat HEAD freshness as evidence that must be surfaced and tested. If the implementation needs a stronger HEAD policy, stop and document it as an owner decision rather than silently inventing one.

## Out of scope

- Automatic controller invocation.
- Automatic creation of an `APPROVE`, `REWORK`, or `BLOCKED` decision.
- Worker self-approval.
- Automatic Git staging.
- Automatic commit or push.
- Merge or branch switching.
- GitHub write actions from the runner.
- Production/deployment actions.
- Destructive Git operations.
- Database/model/migration changes.
- ERP/business feature work.
- Replacing TASK-009 lifecycle authority.
- Signing, remote transport, or cryptographic identity.
- General orchestration redesign.

## Database impact

None. No schema, model, migration, or production database change is authorized.

## Safety requirements

- Stay on `agent-control-foundation`.
- `main` remains non-executable and untouched.
- Existing runner pre/post Git safety checks remain unchanged.
- Worker may not create or apply controller approval authority.
- A decision record must never itself stage, commit, push, merge, deploy, or switch branches.
- `--apply` must be explicit; preview is the default.
- The bridge must reuse existing lifecycle authority and fail closed on unknown states.
- Task mutation, when explicitly applied, is limited to the single `STATUS:` line through the existing lifecycle mechanism.
- No secrets, environment dumps, connection strings, full task bodies, full worker transcripts, or business/customer operational data may be copied into bridge audit/output artifacts.

## Acceptance criteria

- [ ] `APPROVE` maps to requested lifecycle target `APPROVED`.
- [ ] `REWORK` maps to requested lifecycle target `REWORK`.
- [ ] `BLOCKED` maps to requested lifecycle target `BLOCKED`.
- [ ] Preview is the default and does not mutate task or Git state.
- [ ] Explicit `--apply` is required for a lifecycle mutation.
- [ ] Apply reuses TASK-009 lifecycle authority and transition validation.
- [ ] Worker actor cannot use the bridge to approve/rework/block as controller.
- [ ] `APPROVE` cannot bypass an invalid current lifecycle state.
- [ ] Decision, bundle, and task identity mismatches are rejected.
- [ ] Missing or malformed linked evidence is rejected.
- [ ] Branch mismatch is rejected.
- [ ] HEAD evidence is surfaced without silently inventing a new owner policy.
- [ ] Apply changes only the linked task `STATUS:` line.
- [ ] Preview/apply attempts are auditable locally.
- [ ] No commit/push/merge/deploy capability is added.
- [ ] No database/model/migration changes are made.
- [ ] Existing runner, lifecycle, review-bundle, controller-decision, audit, and non-runner tests remain passing.
- [ ] Full pytest suite passes.
- [ ] Architecture documentation is updated.
- [ ] Completion report is written into this task file.

## Test requirements

At minimum test:

1. `APPROVE` decision + controller + task in `REVIEW` → preview permitted for `APPROVED`.
2. Same case + explicit apply → only task `STATUS:` changes to `APPROVED`.
3. `APPROVE` decision + task in `READY` → denied; no mutation.
4. `APPROVE` decision + worker actor → rejected.
5. `REWORK` decision + valid lifecycle state → existing transition rules are used.
6. `BLOCKED` decision + valid non-final lifecycle state → existing transition rules are used.
7. Invalid transition state → denied with clear reason.
8. Missing decision record → rejected.
9. Malformed decision record → rejected.
10. Missing linked review bundle → rejected.
11. Malformed linked review bundle → rejected.
12. Decision/bundle task ID mismatch → rejected.
13. Decision/bundle task filename mismatch → rejected.
14. Current branch differs from bundle branch → rejected.
15. Linked task file identity mismatch → rejected.
16. Preview does not change Git status/HEAD/task file.
17. Apply does not stage, commit, push, merge, deploy, or switch branches.
18. Audit record/reference is produced when available.
19. Existing TASK-009, TASK-010, TASK-011, runner, and non-runner tests remain passing.

Run:

```bash
.venv/bin/python -m pytest tests/ -v
```

## Constraints

- Read and obey `AGENTS.md`.
- Inspect TASK-009 lifecycle, TASK-010 review bundle, and TASK-011 controller decision implementations before coding.
- Stay on `agent-control-foundation`.
- Do not modify `main`.
- Do not commit or push until explicit reviewer approval.
- Keep changes small and reversible.
- Prefer standard-library support and existing project helpers over new dependencies.
- Do not introduce network services or external dependencies.
- If implementation requires a new owner-level policy decision, stop and report instead of inventing it.

## Owner decisions

None required to begin. If a stricter current-HEAD freshness rule is considered necessary, stop and present it as an owner decision rather than silently enforcing it.

## Completion report

### Implemented

### Files changed

### Database changes

### Tests and results

### Assumptions

### Risks / unresolved issues

### Decisions required

### Recommended next step

### git status --short
