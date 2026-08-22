# TASK-021 — End-to-End Controller Orchestration

STATUS: READY

## Objective

Add one governed, resumable orchestration layer that chains the existing TASK-019 through TASK-020 capabilities from a bounded owner goal to safe publication of the current non-`main` feature branch, while preserving every existing authority boundary.

The permanent AdvanCore capability must coordinate, but not duplicate or weaken:

`owner goal → DRAFT task generation → controller DRAFT review/READY decision → governed auto-pipeline → bounded repair → controller implementation review → controller-gated finalization → feature-branch push`

The orchestrator must stop and emit a precise exception whenever external controller/owner authority is absent, an owner decision remains unresolved, repository evidence is stale, or any state is unsafe or ambiguous. It must be restartable from verified durable evidence so the owner or a local operator such as Codex desktop does not have to relay each intermediate result manually.

## Business context

TASK-019 provides governed owner-goal to DRAFT-task generation. TASK-017/TASK-018 provide verified Kimi/Kimi-Swarm execution and bounded repair. TASK-010 through TASK-016 provide controller review, decision, adapter, handoff, and transport boundaries. TASK-020 provides controller-gated exact-scope commit and feature-branch push.

The capabilities exist, but an operator still has to invoke stages separately, locate artifacts, carry identifiers and paths between commands, and decide which command comes next. That stage-by-stage courier work should be removed without making Kimi, Codex, a transport provider, or the orchestration code an authority it does not already possess.

Codex desktop can safely provide local process execution, monitoring, repository inspection, and exception presentation on this Mac. Those conveniences should not be reimplemented inside AdvanCore as a vendor-specific desktop agent, background service, or remote OpenAI integration. AdvanCore must instead expose one deterministic, provider-neutral orchestration command whose checkpoints and authority rules work independently of Codex. Codex may invoke and monitor that command as a local operator, just as a human or another approved automation client could.

## Facts

- GitHub remains the source of truth for code, tasks, architecture decisions, and approved knowledge.
- `advancore.agent_runner` remains the authority and enforcement boundary.
- Kimi/Kimi-Swarm remains an implementation worker or proposal-only planner and cannot approve its own work.
- TASK-019 creates only runner-validated `DRAFT` tasks.
- TASK-009 lifecycle rules reserve `DRAFT → READY`, review decisions, and BLOCKED release to controller/owner authority.
- TASK-017/TASK-018 end at verified `READY_FOR_APPROVAL`; verification is evidence, not approval.
- TASK-020 requires a separately valid controller `APPROVE` decision before lifecycle approval, exact-scope commit, or feature-branch push.
- The current controller adapter and transport boundaries are replaceable and include a local/manual path; no remote controller vendor is required by the architecture.
- Codex desktop can operate the local repository and run the governed CLI, but its availability is an execution convenience rather than an AdvanCore runtime dependency.

## Assumptions

- A controller implementation capable of reviewing bounded artifacts may be local, remote, human-assisted, or AI-assisted, provided it returns decisions through the existing authenticated/validated controller boundary and is not the implementation worker approving its own work.
- The first implementation may pause at controller gates and return a resumable checkpoint when no approved controller adapter/decision is available; removing manual courier work does not authorize fabricated decisions.
- Local Git authentication is configured outside AdvanCore. The orchestrator does not read, store, or manage credentials.
- One orchestration run owns one bounded owner goal and at most one generated task. Multi-task decomposition remains future work.

## Permanent AdvanCore responsibility

AdvanCore must permanently own:

1. The orchestration state machine, allowed transitions, terminal states, and fail-closed policy.
2. Stable correlation of owner goal, generated task, review bundles, handoffs, controller decisions, auto-pipeline evidence, finalization evidence, branch, and HEAD.
3. Deterministic checkpoint persistence, resume validation, idempotency, and stale-evidence detection.
4. Invocation of existing goal-task, lifecycle, controller adapter/transport, auto-pipeline, repair, and finalization APIs.
5. Authority checks: controller/owner decisions remain distinct from worker output and pipeline success.
6. Bounded audit artifacts and a consolidated exception/next-action report.
7. Provider-neutral extension points for planner, implementation worker, and controller adapter/transport selection.
8. The invariant that `main`, merge, deployment, secrets, production systems, and policy decisions remain outside this workflow.

## Local Codex desktop responsibility

Codex desktop may provide, without becoming a required AdvanCore component:

1. Invoke the orchestration CLI from the local repository with owner-selected options.
2. Keep the foreground process/session running, monitor bounded progress, and re-run `--resume` after an external decision is available.
3. Inspect GitHub/local repository state and present owner exceptions or controller-review material clearly.
4. Use already-configured local Git and Kimi tooling through the runner's approved boundaries.
5. Act as, or assist, an independent controller only when explicitly authorized for that role and only by producing a valid decision through the existing controller adapter/transport boundary; it must never bypass the decision record or approve work it performed as the implementation worker.

TASK-021 must not embed Codex SDK calls, ChatGPT APIs, desktop automation, vendor-specific session control, credential management, or a second review protocol in AdvanCore.

## In scope

1. Add `advancore/agent_runner/orchestration.py` as a focused coordinator over existing public runner APIs.
2. Define versioned, bounded models at minimum equivalent to:
   - `OrchestrationPhase`;
   - `OrchestrationStatus`;
   - `OrchestrationCheckpoint`;
   - `OrchestrationConfig`;
   - `OrchestrationResult`.
3. Implement a deterministic phase model equivalent to:
   - `GOAL_VALIDATION`;
   - `TASK_DRAFT_GENERATION`;
   - `AWAITING_TASK_APPROVAL`;
   - `TASK_EXECUTION`;
   - `AWAITING_IMPLEMENTATION_DECISION`;
   - `FINALIZATION`;
   - `PUBLISHED`;
   - `BLOCKED` / `FAILED`.
4. Reuse `generate_goal_task()`, lifecycle helpers, `run_auto_pipeline()`, controller handoff/adapter/transport/reconciliation helpers, and `run_finalization()` rather than copying their validation or Git mutation logic.
5. Accept either:
   - a new bounded owner goal for a new run; or
   - an explicit orchestration run ID/checkpoint for resume.
   Mixing a new goal with resume state must fail closed.
6. Make CLI preview the default. Require an explicit `--apply` (or equivalently clear mutation flag) before planner launch, task writing, lifecycle mutation, worker execution, controller dispatch, finalization, commit, or push.
7. On apply for a new run, invoke TASK-019 goal-task generation and bind the resulting task ID/path to the orchestration checkpoint. The task must remain `DRAFT` until a separately valid controller/owner transition authorizes `DRAFT → READY`.
8. At the task-approval gate:
   - surface the generated task and its unresolved owner decisions;
   - never auto-promote a DRAFT based on generation success;
   - accept only an existing valid controller/owner lifecycle decision through current authority rules;
   - stop as `AWAITING_TASK_APPROVAL` if authority is absent;
   - stop as `BLOCKED` if owner decisions, policy, compliance, secrets, deployment, production, scope expansion, or ambiguous requirements require owner input.
9. After valid `READY`, call the existing auto-pipeline with an explicitly bounded worker and repair budget. Preserve Kimi/Kimi-Swarm as worker-only and preserve the current maximum repair budget.
10. Treat auto-pipeline `READY_FOR_APPROVAL` only as evidence. For every other pipeline terminal state, classify and report the existing repair exhaustion, non-repairable, or failure status without inventing a recovery.
11. Create/reuse the existing review bundle and controller handoff/transport flow for implementation review. Do not create a parallel controller request or decision schema.
12. At the implementation-decision gate:
   - resume only from a valid correlated decision;
   - `APPROVE` may proceed to TASK-020 finalization;
   - `REWORK` may re-enter the existing governed execution/repair path only after the existing lifecycle transition is valid and within a bounded orchestration rework budget;
   - `REJECT`, `BLOCKED`, missing, invalid, conflicting, or stale decisions must stop without publication.
13. Use a small deterministic rework-cycle budget, default `0` and maximum `1`, separate from TASK-018's repair-attempt budget. Exhaustion requires controller/owner intervention.
14. Call `run_finalization()` only with the exact valid controller approval and correlated evidence already verified by TASK-020. Do not duplicate its lifecycle, staging, commit, or push implementation.
15. End successfully only when TASK-020 reports a verified `PUSHED` result for the same current non-`main` branch and the repository is clean and synchronized with `origin/<same-branch>`.
16. Persist one ignored checkpoint per run under `.agent_runner/orchestration/`. Use atomic write/replace behavior so an interrupted write cannot silently become a valid checkpoint.
17. Bind every checkpoint to at minimum:
   - schema version and unique run ID;
   - bounded goal hash/summary, never an unrestricted transcript;
   - task ID and task path once assigned;
   - current phase/status and completed phases;
   - selected planner, worker, controller adapter/transport, repair budget, and rework budget;
   - branch and expected HEAD at each authority-sensitive boundary;
   - safe repository-state fingerprint or exact relevant path set;
   - goal-task artifact, review bundle, handoff, transport request/response, decision, auto artifact, and finalization artifact references when present;
   - attempt counters and bounded blocking reason/next action;
   - whether any task, lifecycle, commit, or push mutation occurred.
18. On every resume, reload authoritative files/artifacts and revalidate their contents. A checkpoint reference alone is never proof of authority or freshness.
19. Make resume idempotent:
   - completed phases are not repeated merely because the command is re-run;
   - planner/worker/controller dispatch is not duplicated when a valid correlated result already exists;
   - finalization is not repeated after a verified push;
   - conflicting duplicate artifacts or decisions fail closed.
20. Capture the checkpoint before and after every external boundary where practical. If interruption occurs after an external action but before checkpoint update, reconcile authoritative Git/artifact state rather than blindly repeating the action.
21. Use an explicit controller adapter/transport selection. Do not silently fall back from an unavailable configured controller to worker self-review or inferred approval.
22. Support local/manual controller mode as a first-class pause/resume path. This permits Codex desktop or a human controller to review and return an existing valid decision without copying stage outputs between unrelated commands.
23. Add a CLI command with an interface equivalent to:

   ```bash
   .venv/bin/python -m advancore.agent_runner orchestrate \
     --goal "<bounded owner goal>" \
     --planner kimi-swarm \
     --worker kimi-swarm \
     --controller manual \
     --repair-attempts 2

   .venv/bin/python -m advancore.agent_runner orchestrate \
     --resume <run-id> --apply
   ```

   Exact option names may vary if a smaller, safer interface is clearer.
24. Preview must show the intended phases, selected replaceable adapters, mutation gates, expected pause points, and prohibited actions without launching any model/tool or writing a checkpoint/task/artifact.
25. Apply must print one consolidated, machine-readable-enough result containing run ID, task, phase, status, completed phases, branch/HEAD binding, evidence paths, controller gate state, mutations performed, blocking reason, owner decision required, and exact next action/resume command.
26. Distinguish terminal outcomes at minimum equivalent to:
   - `PUBLISHED`;
   - `AWAITING_TASK_APPROVAL`;
   - `AWAITING_IMPLEMENTATION_DECISION`;
   - `OWNER_DECISION_REQUIRED`;
   - `REWORK_REQUIRED`;
   - `REWORK_EXHAUSTED`;
   - `NON_REPAIRABLE`;
   - `STALE_EVIDENCE`;
   - `BLOCKED`;
   - `FAILED`.
27. Never use orchestration success to create controller authority. All lifecycle and publication authority must still be established by existing validated records and actor rules.
28. Add deterministic tests for phase sequencing, pause/resume, authority separation, idempotency, crash/reconciliation boundaries, stale evidence, exact API delegation, bounded retries, preview safety, checkpoint validation, and terminal reporting.
29. Update `docs/architecture/AGENT_RUNNER.md` and add `docs/decisions/ADR-021-end-to-end-controller-orchestration.md` documenting the permanent/local split and rejected vendor-dependent alternatives.
30. Run the full pytest suite.
31. Complete this task-file Completion report and stop without self-approving, self-finalizing, merging, or deploying TASK-021.

## Important governance rule

**The orchestrator advances verified state; it does not create authority.**

The orchestrator must never:

- treat goal submission as approval of a generated task;
- treat passing tests, `READY_FOR_APPROVAL`, review-bundle creation, controller dispatch, or transport success as controller approval;
- let Kimi/Kimi-Swarm approve its own task or implementation;
- let the same agent execution role silently change from worker to independent controller for its own work;
- manufacture, edit, reinterpret, or default a missing controller decision to `APPROVE`;
- bypass TASK-009 lifecycle transitions or TASK-020 finalization gates;
- trust checkpoint contents without revalidating source artifacts and Git state;
- retry external actions without idempotency/reconciliation checks;
- broaden allowed changed-file scope to make a failed run pass;
- commit or push `main`, merge, force-push, tag, release, or deploy;
- access, persist, or transmit credentials, secrets, environment dumps, production data, customer data, or unrestricted model transcripts;
- continue when owner/business/compliance/policy authority is required;
- depend on Codex, ChatGPT, OpenAI, Kimi, or any single vendor for the governance model.

## Explicitly out of scope

- Automatic creation of controller approval decisions.
- Autonomous owner, commercial, compliance, security-policy, credential, deployment, or production decisions.
- A new controller protocol, lifecycle model, review schema, worker adapter, or publication implementation.
- Remote ChatGPT/OpenAI API or Codex SDK integration.
- Codex desktop control, browser automation, GUI automation, or session management inside AdvanCore.
- Claw integration.
- Background daemon, scheduler, webhook listener, long-running server, or hosted control plane.
- Multi-task/epic decomposition or parallel task execution.
- More than one bounded controller rework cycle.
- Merge or pull-request auto-merge to `main`.
- Deployment, releases, tags, production database access, or production-system mutation.
- Git credential, token, SSH key, or secret management.
- Force push, reset, rebase, history rewrite, branch deletion, or remote modification.

## Allowed changed-file scope

The TASK-021 implementation worker may change only these seven paths unless it stops and reports why an additional path is required:

1. `advancore/agent_runner/orchestration.py` (new)
2. `advancore/agent_runner/__init__.py`
3. `advancore/agent_runner/__main__.py`
4. `tests/test_orchestration.py` (new)
5. `docs/architecture/AGENT_RUNNER.md`
6. `docs/decisions/ADR-021-end-to-end-controller-orchestration.md` (new)
7. `tasks/TASK-021-end-to-end-controller-orchestration.md`

No other file is authorized for modification. If implementation reveals that an existing public API is insufficient, stop before changing its module and request controller approval for a specifically named scope expansion. Do not copy that module's logic into the orchestrator as a workaround.

## Database impact

None. No schema, model, migration, production database, or business-data mutation is authorized.

Orchestration checkpoints are bounded ignored local artifacts, not application database records and not a substitute for GitHub source-of-truth.

## Safety requirements

- Read and obey `AGENTS.md`.
- Stay on `agent-control-foundation`.
- GitHub remains source-of-truth.
- `agent_runner` remains the sole governance enforcement boundary.
- `main` remains untouched and non-executable.
- Reuse existing module APIs and artifacts; coordination must not fork their rules.
- Planner, worker, controller, and local operator roles must remain explicit in configuration and audit output.
- Preserve TASK-009 through TASK-020 authority, validation, repair, controller, and publication semantics unchanged.
- Unknown, malformed, stale, conflicting, duplicate, unsafe, or ambiguous state fails closed.
- Checkpoints contain bounded metadata only and remain gitignored.
- Use standard-library-first implementation and no new dependency unless separately approved.
- Keep mutations small, ordered, auditable, and recoverable through explicit resume/reconciliation.

## Acceptance criteria

- [ ] A focused provider-neutral orchestration module exists.
- [ ] One command can coordinate the existing goal-task, lifecycle, auto-pipeline, controller, and finalization components.
- [ ] Preview is the default and performs no model launch or repository/artifact mutation.
- [ ] Apply requires an explicit mutation flag.
- [ ] A new run generates at most one runner-owned DRAFT task.
- [ ] DRAFT never advances without valid controller/owner authority.
- [ ] Unresolved owner decisions produce an explicit owner-required stop.
- [ ] Kimi/Kimi-Swarm remains planner proposal-only or implementation worker-only.
- [ ] Auto-pipeline verification is never treated as approval.
- [ ] Controller review reuses existing handoff/adapter/transport and decision records.
- [ ] Missing or invalid controller authority pauses or blocks without downstream mutation.
- [ ] Valid controller REWORK is bounded and cannot expand scope automatically.
- [ ] Valid controller APPROVE alone may enter existing TASK-020 finalization.
- [ ] Finalization logic is delegated to TASK-020, not copied.
- [ ] Success requires verified clean synchronization with `origin/<current-feature-branch>`.
- [ ] `main`, merge, deployment, force push, and credential management remain impossible.
- [ ] Durable checkpoint state is bounded, versioned, atomic, and correlated to authoritative evidence.
- [ ] Resume reloads and revalidates authoritative artifacts and Git state.
- [ ] Completed/external phases are idempotent and are not blindly repeated.
- [ ] Interrupted external actions are reconciled before retry.
- [ ] Conflicting decisions/artifacts fail closed.
- [ ] Repair and rework budgets are distinct, bounded, and reported.
- [ ] Local/manual controller pause/resume works without vendor-specific integration.
- [ ] Codex is documented as an optional local operator, not a governance dependency.
- [ ] Consolidated output provides one exact next action instead of requiring stage-by-stage couriering.
- [ ] Exact seven-file implementation scope is respected.
- [ ] Existing tests remain passing.
- [ ] Full pytest suite passes.
- [ ] Architecture documentation and ADR are updated.
- [ ] Completion report is written into this task file.

## Test requirements

At minimum test:

1. Preview with a valid goal shows the plan and writes/launches nothing.
2. Apply with an empty or oversized goal fails before any external action.
3. New apply delegates exactly once to goal-task generation and binds the returned task.
4. Generated DRAFT pauses at `AWAITING_TASK_APPROVAL` without valid authority.
5. Owner decisions in the generated task force `OWNER_DECISION_REQUIRED`.
6. Worker/planner output cannot authorize `DRAFT → READY`.
7. Valid controller/owner `DRAFT → READY` authority resumes execution.
8. Resume with a new/different goal fails closed.
9. Resume with unknown, malformed, or unsupported checkpoint schema fails closed.
10. Resume with task ID/path mismatch fails closed.
11. Resume with branch or HEAD mismatch reports stale evidence before mutation.
12. Resume with changed-path/fingerprint mismatch fails closed.
13. Completed goal-task generation is not invoked again on resume.
14. READY task delegates to auto-pipeline with the configured worker and bounded repair budget.
15. Auto-pipeline `READY_FOR_APPROVAL` creates/reuses the existing review/handoff flow but does not approve.
16. Repair exhausted/non-repairable auto results stop with the corresponding terminal status.
17. Missing controller decision pauses at `AWAITING_IMPLEMENTATION_DECISION`.
18. Worker-authored, malformed, mismatched, or stale decision blocks.
19. Controller `REJECT`/`BLOCKED` never calls finalization.
20. Controller `REWORK` follows valid lifecycle authority and one bounded rework cycle only.
21. Rework-budget exhaustion requires controller/owner intervention.
22. Controller `APPROVE` with matching evidence delegates exactly once to finalization.
23. Orchestrator never directly stages, commits, or pushes.
24. Finalization failure is reported without being retried blindly.
25. Verified `PUSHED` produces terminal `PUBLISHED` and cannot finalize again on resume.
26. Duplicate/conflicting controller artifacts fail closed.
27. Simulated interruption after planner/worker/controller dispatch reconciles evidence before any repeat.
28. Simulated interruption after local commit detects finalization state and never creates a second commit.
29. Checkpoint writes are atomic and a partial/corrupt checkpoint is rejected.
30. Checkpoint/audit payload excludes raw prompts, transcripts, source contents, secrets, credentials, and environment dumps.
31. Explicit manual controller mode returns a precise artifact/decision requirement and resume command.
32. Provider selection is explicit; unavailable configured adapters do not fall back to inferred approval.
33. No code path targets `main`, merge, deploy, tag, force push, or remote mutation.
34. Existing TASK-009 through TASK-020 tests remain passing.

Run:

```bash
.venv/bin/python -m pytest tests/ -v
```

## Constraints

- Implement orchestration, not a second governance system.
- Keep every existing authority boundary fail-closed.
- Do not add vendor-specific controller or desktop dependencies.
- Do not broaden public APIs or file scope without stopping for approval.
- Do not self-approve or self-finalize TASK-021 using the feature being implemented.

## Owner decisions

The owner has decided that:

- owner involvement should become exception-based rather than stage-by-stage;
- `agent_runner` remains the authority boundary;
- Kimi/Kimi-Swarm remains an implementation worker;
- GitHub remains source-of-truth;
- fail-closed approval boundaries must not be weakened;
- Codex desktop may provide local execution/control but must not become a required vendor dependency;
- TASK-021 must not merge to `main` or deploy.

One controller decision remains required before implementation: review this DRAFT specification and authorize `DRAFT → READY`. No implementation, controller-approval automation, merge, or deployment authority is implied by this task's creation.

## Completion report

### Implemented

### Files changed

### Database changes

### Tests and results

### Assumptions

### Risks / unresolved issues

### Decisions required

### Recommended next step
