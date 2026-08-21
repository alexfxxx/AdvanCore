# TASK-019 — Goal-to-Task Generation Foundation

STATUS: APPROVED

## Objective

Add a governed **owner-goal → task-draft** generation layer to the existing Agent Control system so a bounded natural-language owner goal can be converted into a deterministic AdvanCore task file without requiring the owner to manually draft/courier the task specification between ChatGPT, Kimi, GitHub, and the runner.

The generated task must begin at `STATUS: DRAFT`. A planner/model may propose task content, but it must remain **untrusted planning assistance only**. The AdvanCore runner is responsible for validating the proposal, assigning the task ID, rendering the canonical task document, enforcing path/scope safety, and writing the task file. The planner must never be allowed to mark its own task `READY`, execute the generated task, approve it, stage it, commit it, push it, merge it, or deploy it.

This task must preserve GitHub as source-of-truth and the local/hosted AdvanCore runner as the governance authority. It must build on TASK-017/TASK-018 rather than redesigning earlier controller, lifecycle, transport, review, or worker architecture.

## Business context

The critical project objective is to remove the owner from the repetitive development courier loop as far as safely possible.

The current system already automates:

`task validation → Kimi/Kimi-Swarm implementation → post-worker Git verification → review bundle → full pytest → diff-check → exact scope verification → bounded autonomous repair → READY_FOR_APPROVAL`

The remaining front-end courier burden is that a human/controller still has to manually turn an owner goal into a complete governed `TASK-###` specification before the auto-pipeline can begin.

TASK-019 introduces the missing front door:

`Owner goal → bounded planner proposal → runner validation → deterministic DRAFT task → controller review`

A later task may connect controller review/promotion and safe task publication more tightly. TASK-019 itself must stop at a validated `DRAFT` task and must not broaden publication or approval authority.

## Governance model

The authoritative roles for TASK-019 are:

- **Owner**: supplies the goal and remains the ultimate authority for business/policy decisions.
- **Planner** (`kimi` / `kimi-swarm` / future replaceable planner): may inspect approved repository context and propose task content only.
- **AdvanCore runner**: validates the planner proposal, assigns the next task ID, renders/writes the canonical DRAFT task, verifies that planner execution did not mutate the repository, and produces bounded audit/artifact evidence.
- **Controller/reviewer**: remains the authority for `DRAFT → READY` through the existing lifecycle rules.
- **Worker/swarm**: may execute only a separately reviewed executable task (`READY`/`REWORK`) through the existing runner/auto-pipeline.

A generated DRAFT is **not executable authority**.

## In scope

1. Add `advancore/agent_runner/goal_task.py` as a focused goal-to-task generation module.
2. Define bounded data/result models, at minimum equivalent to:
   - `OwnerGoal` or normalized goal input;
   - `GoalTaskProposal` (untrusted planner proposal);
   - `GoalTaskGenerationStatus`;
   - `GoalTaskGenerationResult`.
3. Accept a bounded natural-language owner goal. The implementation must:
   - reject empty/whitespace-only input;
   - impose a deterministic maximum length;
   - preserve the goal as bounded planning context without treating embedded instructions as controller authority;
   - never interpolate the goal into shell execution.
4. Add a canonical planner instruction for `kimi` / `kimi-swarm` that clearly states:
   - planning only;
   - do not modify repository files;
   - do not stage/commit/push/merge/deploy;
   - do not change branches or HEAD;
   - do not access credentials/secrets/production data;
   - do not self-approve or mark a task READY;
   - return only one bounded structured task proposal between deterministic delimiters/markers.
5. Define a deterministic, versioned proposal schema. At minimum the planner proposal should contain bounded forms of:
   - title;
   - objective;
   - business context;
   - confirmed facts / explicit assumptions separation;
   - in-scope work;
   - explicit out-of-scope work;
   - proposed allowed changed-file scope;
   - database impact;
   - acceptance criteria;
   - test requirements;
   - constraints / safety requirements;
   - owner decisions or unresolved policy questions;
   - recommended worker (`kimi` or `kimi-swarm`) if useful.
6. The planner must NOT control:
   - task ID;
   - task status;
   - lifecycle transitions;
   - branch choice;
   - commit/push/merge/deploy behavior;
   - controller approval.
7. Parse planner output fail-closed. Reject:
   - missing or duplicate proposal markers;
   - malformed JSON/structured payload;
   - unknown schema version;
   - unknown/unexpected top-level fields if a strict schema is used;
   - missing required fields;
   - oversized fields/lists;
   - absolute paths, parent traversal, empty paths, or unsafe scope paths;
   - task IDs/statuses supplied by the planner where not permitted;
   - ambiguous or conflicting proposal content that cannot be safely normalized.
8. Before planner execution, capture repository branch/HEAD/worktree state using existing Git helpers.
9. Planner execution must begin only when the repository is on the approved non-`main` branch and the worktree is clean.
10. After planner execution and **before creating the task file**, verify fail-closed that the planner did not mutate tracked/untracked repository content, stage files, move HEAD, change branch, or alter remotes. Any planner-created repository change is a generation failure and no task file may be written.
11. Reuse the existing `WorkerAdapter` boundary for planner execution where practical. `KimiSwarmWorkerAdapter` may be used as a planner, but its output is a proposal only and never task authority.
12. Deterministically assign the next task number from existing `tasks/TASK-*.md` files. Requirements:
   - planner cannot choose the number;
   - use the next unused numeric task ID;
   - prevent overwrite/collision;
   - fail if the target path appears unexpectedly between planning and write;
   - keep task numbering stable and explainable.
13. Generate a safe filename slug from the validated proposal title. Reject/normalize unsafe filename characters and keep the path strictly under `tasks/`.
14. Render the final task using a canonical runner-owned template consistent with existing task conventions. The generated task must include, at minimum:
   - `# TASK-### — <title>`;
   - `STATUS: DRAFT`;
   - Objective;
   - Business context;
   - Facts / Assumptions where applicable;
   - In scope;
   - Explicitly out of scope;
   - Allowed changed-file scope;
   - Database impact;
   - Safety requirements;
   - Acceptance criteria;
   - Test requirements;
   - Constraints;
   - Owner decisions;
   - Completion report skeleton.
15. Inject fixed governance language owned by the runner, not the planner, including:
   - GitHub remains source-of-truth;
   - `main` remains untouched unless explicitly approved;
   - worker/swarm cannot approve its own work;
   - no automatic staging/commit/push/merge/deploy;
   - generated task is DRAFT and cannot execute until valid `DRAFT → READY` controller/owner transition;
   - unknown/unsafe/ambiguous states fail closed.
16. The final rendered task must never silently omit `Owner decisions`. If the proposal identifies unresolved business/compliance/credential/production/deployment decisions, preserve them explicitly for controller/owner review.
17. Add a goal-to-task generation artifact under ignored `.agent_runner/goal_task/` containing only bounded metadata such as:
   - goal hash/short bounded goal summary (not unrestricted raw transcripts);
   - planner type;
   - proposal schema version;
   - assigned task ID/path;
   - pre/post planner branch/HEAD;
   - validation result/status;
   - owner-decision count;
   - whether a task file was written;
   - no-publication-performed flag.
18. Do not store full Kimi transcripts, environment dumps, secrets, credentials, customer data, or arbitrary repository content in the artifact.
19. Add CLI support under a focused command such as `goal-task` with safe modes. A compatible target interface is:
   - `goal-task --goal "..." --planner dry-run`
   - `goal-task --goal "..." --planner kimi-swarm --execute`
   Exact option names may vary if a smaller safer interface is clearer.
20. Default CLI behavior must be non-executing/dry-run unless an explicit execution flag is provided.
21. A dry-run must validate the owner goal, identify the next candidate task ID, and show intended planner/task-generation behavior without launching Kimi or writing a task file.
22. An execute run may invoke the selected planner and write **only the new DRAFT task file** after all planner-output and repository-integrity checks pass.
23. The command must end with one consolidated result including:
   - goal accepted/rejected;
   - planner type and success;
   - proposal validation result;
   - assigned task ID/path;
   - generated lifecycle state (`DRAFT` only);
   - owner decisions requiring review;
   - repository-integrity checks;
   - artifact path;
   - explicit statement that no stage/commit/push/merge/deploy/approval occurred;
   - next action: controller review / `DRAFT → READY` decision.
24. Do not automatically call the TASK-017/TASK-018 `auto` pipeline on the generated task in TASK-019.
25. Do not automatically perform `DRAFT → READY`.
26. Add deterministic tests for goal validation, proposal parsing, strict schema, task-ID allocation, path safety, planner mutation detection, deterministic rendering, owner-decision preservation, dry-run behavior, no-publication guarantees, and CLI behavior.
27. Update `docs/architecture/AGENT_RUNNER.md` and add `docs/decisions/ADR-019-goal-to-task-generation.md`.
28. Run the full pytest suite.
29. Complete this task-file Completion report and stop without staging, committing, pushing, merging, or deploying.

## Important governance rule

**The planner proposes. The runner constructs. The controller authorizes execution.**

The goal-to-task layer must never:

- let Kimi/Kimi-Swarm assign task authority to itself;
- let planner output directly become an executable `READY` task without controller/owner review;
- trust a planner-supplied task ID or lifecycle status;
- launch implementation of the generated task automatically;
- stage, commit, push, merge, tag, deploy, switch branches, reset, rebase, or rewrite history;
- access credentials, secrets, tokens, production data, or production databases;
- modify `main`;
- hide owner decisions or compliance/security concerns;
- continue after planner repository mutation or ambiguous state.

## Explicitly out of scope

- Automatic `DRAFT → READY` controller approval.
- Automatic execution of the generated task.
- Automatic staging/commit/push/merge/publication of the generated task file.
- Automatic changes to `main`.
- Remote ChatGPT/OpenAI controller API integration.
- Kimi/Claw as controller authority.
- Claw integration.
- Webhooks/background daemons/schedulers.
- Credentials/API keys/OAuth/secret storage.
- Deployment or production database access.
- Unlimited task decomposition into multiple executable tasks.
- Parent/epic planning across many tasks; this task generates one bounded DRAFT task per accepted goal invocation.

## Allowed changed-file scope

The TASK-019 implementation worker may change only these seven paths unless it stops and reports why an additional path is required:

1. `advancore/agent_runner/goal_task.py` (new)
2. `advancore/agent_runner/__init__.py`
3. `advancore/agent_runner/__main__.py`
4. `tests/test_goal_task.py` (new)
5. `docs/architecture/AGENT_RUNNER.md`
6. `docs/decisions/ADR-019-goal-to-task-generation.md` (new)
7. `tasks/TASK-019-goal-to-task-generation.md`

No other file is authorized for modification in TASK-019. If implementation genuinely requires another file, stop before changing it and report the need for reviewer approval.

## Database impact

None. No schema, model, migration, or production database change is authorized for TASK-019 itself.

A generated future task may propose database work only as explicit task scope/impact; that proposal remains DRAFT and requires controller/owner review before execution.

## Safety requirements

- Read and obey `AGENTS.md`.
- Stay on `agent-control-foundation`.
- `main` remains untouched and non-executable.
- GitHub remains source-of-truth.
- The AdvanCore runner remains the enforcement boundary.
- Reuse existing Git snapshot/validation helpers and worker-adapter abstractions where practical.
- Preserve TASK-009 lifecycle authority: only controller/owner may move `DRAFT → READY`.
- Preserve TASK-017/TASK-018 auto-pipeline and repair semantics unchanged.
- Preserve TASK-010 through TASK-016 controller/transport authority boundaries unchanged.
- Unknown, malformed, stale, unsafe, conflicting, ambiguous, or unauthorized input fails closed.
- Keep implementation standard-library-first and dependency-free unless an existing dependency is already approved.
- Do not add a second lifecycle model or a parallel publication model.

## Acceptance criteria

- [ ] Bounded owner-goal input model/validation exists.
- [ ] Replaceable planner invocation uses existing worker-adapter boundary or an equally bounded compatible boundary.
- [ ] Planner is explicitly proposal-only and cannot assign task ID/status/authority.
- [ ] Versioned structured proposal schema exists.
- [ ] Malformed/unknown/oversized/unsafe planner output fails closed.
- [ ] Planner repository mutation is detected before any task write.
- [ ] Planner cannot stage files, move HEAD, change branch, or leave arbitrary repository changes without generation failing.
- [ ] Next task ID is assigned deterministically by the runner.
- [ ] Task filename is safely slugged and cannot escape `tasks/`.
- [ ] Generated task uses `STATUS: DRAFT` only.
- [ ] Generated task includes exact allowed changed-file scope.
- [ ] Generated task includes fixed runner-owned governance language.
- [ ] Owner decisions are preserved explicitly.
- [ ] Generated task is not executed automatically.
- [ ] No `DRAFT → READY` transition occurs automatically.
- [ ] No staging/commit/push/merge/deploy occurs.
- [ ] Dry-run performs no planner launch and writes no task.
- [ ] Execute mode writes only the generated DRAFT task after validation.
- [ ] Bounded goal-task artifact/audit metadata is produced without full transcripts/secrets.
- [ ] CLI prints a consolidated controller-review result.
- [ ] Exact seven-file TASK-019 implementation scope is respected.
- [ ] Existing tests remain passing.
- [ ] Full pytest suite passes.
- [ ] Architecture documentation and ADR are updated.
- [ ] Completion report is written into this task file.

## Test requirements

At minimum test:

1. Empty goal → rejected before planner launch.
2. Oversized goal → rejected before planner launch.
3. Valid goal dry-run → next task ID reported; no planner launch; no task file written.
4. Valid planner proposal → parsed and validated.
5. Unknown proposal schema/version → rejected.
6. Missing required proposal field → rejected.
7. Unexpected planner-controlled task ID/status/authority field → rejected if present/disallowed.
8. Oversized proposal field/list → rejected.
9. Unsafe scope absolute path → rejected.
10. Scope parent traversal → rejected.
11. Duplicate/empty scope path → rejected or deterministically normalized according to documented policy.
12. Planner output missing/duplicate deterministic proposal markers → rejected.
13. Planner returns malformed JSON → rejected.
14. Planner modifies tracked repository file → generation fails; no task written.
15. Planner creates unexpected untracked repository file outside ignored goal-task artifacts → generation fails; no task written.
16. Planner stages a path → generation fails; no task written.
17. Planner changes HEAD/branch → generation fails; no task written.
18. Runner, not planner, assigns next task ID.
19. Existing highest task `TASK-019` → first post-TASK-019 generated task candidate is `TASK-020`.
20. Collision on candidate task path → fail closed; never overwrite.
21. Unsafe title characters are safely slugged.
22. Generated markdown contains `STATUS: DRAFT` exactly once.
23. Generated markdown contains required governance sections and exact allowed scope.
24. Generated markdown preserves unresolved owner decisions.
25. Generated DRAFT is not executable by existing validation/auto pipeline until controller/owner transitions it to READY.
26. Goal-task generation does not invoke task implementation worker execution after creation.
27. No Git add/commit/push/merge/checkout/switch/reset/rebase command is invoked by goal-task generation.
28. No lifecycle transition is applied by goal-task generation.
29. Artifact contains bounded metadata only and no full planner stdout/stderr transcript.
30. CLI dry-run and execute modes report correct terminal states and next controller action.
31. Existing TASK-017/TASK-018 and earlier runner tests remain passing.

Run:

```bash
.venv/bin/python -m pytest tests/ -v
```

## Constraints

- Inspect `task.py`, `lifecycle.py`, `worker.py`, TASK-017/TASK-018 auto pipeline, existing CLI wiring, and task template before coding.
- Do not modify `main`.
- Do not commit or push until explicit reviewer approval.
- Do not add automatic task publication or automatic lifecycle promotion in TASK-019.
- Do not let planner-generated content bypass deterministic runner validation/rendering.
- Do not broaden Kimi/Kimi-Swarm authority.
- Do not introduce remote controller/API/Claw integration in this task.
- Do not expand beyond the exact seven-file TASK-019 implementation scope without stopping for reviewer approval.

## Owner decisions

None required to begin.

TASK-019 deliberately keeps generated tasks at `DRAFT`. A later task may reduce the remaining controller/owner interaction by connecting generated drafts to the existing controller decision/lifecycle path and/or a narrowly-scoped task-publication flow, but that authority expansion is not part of TASK-019.

## Completion report

- **Implemented**
  - Added `advancore/agent_runner/goal_task.py` with bounded owner-goal
    validation, versioned planner proposal parsing/validation, deterministic
    task-ID assignment, safe title slugging, canonical `STATUS: DRAFT` task
    rendering, pre/post planner repository-mutation detection, bounded artifact
    writing, and consolidated report formatting.
  - Added `goal-task` CLI subcommand to `advancore/agent_runner/__main__.py`
    with `--goal`, `--planner {dry-run,kimi,kimi-swarm}`, and `--execute`.
  - Exported new public symbols from `advancore/agent_runner/__init__.py`.
  - Added `tests/test_goal_task.py` covering goal validation, proposal parsing,
    schema validation, unsafe scope rejection, mutation detection, task
    rendering, dry-run/execute behaviour, CLI behaviour, and governance
    guarantees.
  - Updated `docs/architecture/AGENT_RUNNER.md` with section 15 describing the
    goal-to-task generation layer.
  - Added `docs/decisions/ADR-019-goal-to-task-generation.md`.

- **Files changed**
  1. `advancore/agent_runner/goal_task.py` (new)
  2. `advancore/agent_runner/__init__.py`
  3. `advancore/agent_runner/__main__.py`
  4. `tests/test_goal_task.py` (new)
  5. `docs/architecture/AGENT_RUNNER.md`
  6. `docs/decisions/ADR-019-goal-to-task-generation.md` (new)
  7. `tasks/TASK-019-goal-to-task-generation.md`

- **Database changes**
  - None.

- **Tests executed and results**
  - `tests/test_goal_task.py`: 53 passed.
  - Full suite: `472 passed in 6.69s`.

- **Planner proposal policy chosen**
  - Planner is untrusted planning assistance only.
  - Planner receives a canonical instruction that forbids repository mutation,
    authority assignment, and self-approval.
  - Planner returns a single JSON proposal between deterministic markers.
  - Runner enforces schema version `advancore-goal-task-proposal-v1`, rejects
    unknown/missing/forbidden/oversized fields and unsafe paths, and ignores any
    planner-supplied task ID or status.

- **Goal/proposal bounds chosen**
  - Owner goal max length: 2000 normalized characters.
  - Title max length: 120 characters.
  - Text fields max length: 4000 characters.
  - List items max length: 500 characters.
  - List max length: 100 items.
  - Scope path max length: 260 characters.
  - Scope list max length: 50 items.
  - Filename slug max length: 60 characters.

- **Assumptions**
  - The existing `WorkerAdapter` boundary and Git snapshot helpers are suitable
    for planner invocation and integrity verification.
  - Kimi Code's `kimi --prompt` mode remains a suitable bounded invocation.
  - Controller/owner review remains the authority for `DRAFT -> READY`.

- **Risks / unresolved issues**
  - Real planner output quality depends on the underlying model and the
    canonical instruction; the runner fails closed on malformed/unsafe output.
  - A future task may connect generated drafts to the existing controller
    decision/lifecycle path more tightly.

- **Decisions required**
  - Controller/owner must review generated DRAFT task(s) and approve the
    `DRAFT -> READY` transition before any worker execution.

- **Recommended next step**
  - Review the generated DRAFT task(s) and, when appropriate, use the existing
    `transition` subcommand with `--actor controller --to READY --apply` to
    promote a generated task to executable status.

- **`git status --short`**
  ```
   M advancore/agent_runner/__init__.py
   M advancore/agent_runner/__main__.py
   M docs/architecture/AGENT_RUNNER.md
   M tasks/TASK-019-goal-to-task-generation.md
  ?? advancore/agent_runner/goal_task.py
  ?? docs/decisions/ADR-019-goal-to-task-generation.md
  ?? tests/test_goal_task.py
  ```
