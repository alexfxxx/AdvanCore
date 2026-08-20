# TASK-005 — Local Agent Runner / Orchestrator Foundation

STATUS: READY

## Objective
Create the first safe local Agent Runner foundation for AdvanCore so controlled development work can move toward automated task discovery, validation, worker instruction, execution planning, and approval gates without giving the runner unrestricted authority over Git, the operating system, databases, or production systems.

This task establishes the orchestration control plane and safety model. It is not yet permission for fully unattended autonomous development.

## Business context
AdvanCore's intended development operating model is:

`Alex (owner) -> ChatGPT (architect/controller/reviewer) -> GitHub (source of truth) -> Local Agent Runner -> Kimi Code (worker) -> tests/results -> GitHub -> independent review`

Today Alex manually copies instructions and results between ChatGPT and Kimi. That manual relay is the next major bottleneck after TASK-001 through TASK-004 established repository discovery, tests, migrations, and persistence/service conventions.

The runner should eventually remove routine relay work while preserving human control over high-impact actions.

## Facts
- GitHub is the source of truth for approved code, architecture, migrations, task specifications, and agent-control artifacts.
- The controlled development branch is currently `agent-control-foundation`.
- `main` must not be modified or merged autonomously.
- Task files live under `tasks/` and use status values defined in `tasks/README.md`.
- Agents may work only on tasks marked `READY` or `REWORK`.
- Kimi Code is the current local coding/execution worker.
- GitHub CLI authentication and HTTPS Git operations work in the current local environment.
- The project already has automated pytest coverage and an Alembic migration framework.
- TASK-004 established the persistence/service foundation; TASK-005 must not expand ERP business functionality.

## Architectural intent
Create a small local orchestration package with explicit boundaries:

`GitHub/local repository task state -> Runner validation -> Execution plan -> Worker adapter -> Result capture -> Approval gate`

The runner must be policy-driven and fail closed. If a safety precondition is not satisfied, it must stop rather than guess, repair, force, reset, merge, or broaden scope.

## Mandatory safety principles
1. **Dry-run first.** The default command must not execute Kimi or modify Git state.
2. **Never operate on `main`.** If the current branch is `main`, stop with a clear error.
3. **Clean working tree required before launch planning.** Uncommitted changes must block worker launch unless a future task explicitly defines a safe exception.
4. **Only READY/REWORK tasks are executable.** DRAFT, REVIEW, APPROVED, BLOCKED, or unknown status must stop.
5. **One bounded task at a time.** The runner must not combine multiple task files into one worker instruction.
6. **No autonomous merge to main.** No merge command belongs in the first runner foundation.
7. **No destructive Git commands.** Do not use or expose automatic `reset --hard`, forced checkout, forced push, branch deletion, or history rewrite.
8. **No secrets.** Do not read, print, copy, log, or commit `.env`, tokens, credentials, or production data.
9. **No production/destructive DB actions.** The runner must not run database drops/resets or production migrations.
10. **No self-approval.** Worker completion and successful tests do not equal review acceptance.
11. **High-impact actions remain gated.** Commit, push, merge, deployment, destructive operations, secrets access, compliance-rule changes, and commercial-rule changes require explicit policies/approval gates.
12. **Fail closed.** Unknown state or unsupported worker behavior must stop and report rather than improvise.

## In scope
1. Inspect existing governance and task files before implementation:
   - `AGENTS.md`
   - `MASTER_SPEC.md`
   - `CURRENT_STATE.md`
   - `tasks/README.md`
   - `tasks/TASK_TEMPLATE.md`
   - TASK-004 architecture/ADR where relevant.
2. Create a small Python package for the local runner, preferably under `advancore/agent_runner/` unless repository evidence supports a clearly better bounded location.
3. Implement task-file discovery from the checked-out repository.
4. Parse enough task metadata to identify:
   - task filename/id,
   - task title,
   - status.
5. Provide deterministic selection of a requested task by ID/path. Do **not** silently choose among multiple READY tasks unless the selection rule is explicitly documented and unambiguous.
6. Implement repository safety validation using safe read-only Git commands, including at minimum:
   - repository root detection,
   - current branch,
   - working-tree cleanliness,
   - detection/blocking of `main`,
   - confirmation that the selected task file exists and has an allowed status.
7. Build the canonical bounded Kimi instruction from repository state. It should be functionally equivalent to:

   ```text
   Read AGENTS.md.

   Execute tasks/TASK-00X-....md completely.

   Do not commit or push until explicitly approved.

   Stop with the completion report and git status.
   ```

   The runner should reference the task file rather than embedding the full task specification into the prompt.
8. Define a worker-adapter interface/boundary so Kimi is a replaceable worker rather than hard-coded throughout orchestration logic.
9. Inspect the locally installed Kimi CLI safely (`kimi --help` or equivalent help-only command) to determine supported invocation modes.
10. Implement a **dry-run/planning adapter** that shows exactly what would be launched without executing the worker.
11. If and only if the installed Kimi CLI exposes a clearly supported, safe invocation mode suitable for bounded execution, a minimal Kimi adapter MAY be added behind an explicit non-default execution flag. If safe invocation semantics cannot be verified, stop at the adapter boundary and report the limitation; do not invent CLI flags or automate terminal keystrokes.
12. Implement an explicit runner state/result model sufficient to represent at least:
   - task discovered,
   - validation passed/failed,
   - execution planned,
   - worker launch attempted/not attempted,
   - worker completed/failed/unknown,
   - awaiting owner/reviewer approval.
13. Provide a CLI entry point or module command with a small, understandable interface. At minimum support a dry-run/planning command for a specific task, for example conceptually:

   ```bash
   .venv/bin/python -m advancore.agent_runner plan TASK-005
   ```

   Exact syntax may differ if documented and tested.
14. The plan output must clearly show:
   - selected task,
   - task status,
   - branch,
   - working-tree state,
   - safety validation outcome,
   - generated worker instruction,
   - actions that are allowed,
   - actions that remain gated.
15. Add automated tests for task parsing, task status gating, branch gating, dirty-worktree gating, prompt generation, and dry-run behavior.
16. Tests must mock/substitute subprocess/Git/Kimi interactions where practical and must not depend on production credentials.
17. Document the architecture and permission model in `docs/architecture/AGENT_RUNNER.md`.
18. Add an ADR under `docs/decisions/` covering the local runner's fail-closed permission model and worker-adapter approach.
19. Preserve existing application behavior and existing tests.
20. Produce the standard completion report.

## Out of scope
- Autonomous merge to `main`.
- Automatically approving completed work.
- Automatically changing task status in GitHub.
- Automatically creating or merging pull requests.
- Production deployment.
- Production database access or migrations.
- Destructive database operations.
- Reading or managing secrets.
- Git force push, hard reset, branch deletion, history rewrite, or other destructive recovery automation.
- Automatically resolving merge conflicts.
- Automatically editing task scope.
- Commercial, pricing, compliance, legal, payroll, finance, transport, or other business-rule decisions.
- New ERP/business features or UI pages.
- Replacing Kimi with a new coding model/provider.
- Multi-agent swarms.
- Remote/cloud runner infrastructure.
- Background daemon/service operation.
- Scheduling/continuous monitoring.
- Unattended commit/push unless separately authorised in a later controlled task.
- Large orchestration frameworks (Temporal, Airflow, Celery, Kubernetes, etc.).
- A general-purpose shell execution agent.

## Git / repository impact
No branch merge is permitted.

The implementation may add runner source code, tests, and documentation on `agent-control-foundation` only.

The runner itself must use read-only Git operations by default in this task. Any worker execution capability, if safely implemented, must still leave commit/push gated and must not mutate Git history autonomously.

## Database impact
None expected.

No model changes or Alembic revisions should be required. If implementation unexpectedly requires schema changes, stop and report rather than expanding scope.

## Acceptance criteria
- [ ] Runner package/module exists and imports successfully.
- [ ] A specific task can be discovered and parsed from `tasks/`.
- [ ] Task status is validated and non-READY/non-REWORK tasks are rejected.
- [ ] Current Git branch is detected.
- [ ] `main` is rejected as an execution branch.
- [ ] Dirty working tree is detected and blocks launch planning/execution.
- [ ] Canonical Kimi worker instruction is generated from the selected task path.
- [ ] Worker execution is abstracted behind a replaceable adapter/interface.
- [ ] Default behavior is dry-run/non-executing.
- [ ] Dry-run output clearly shows task, branch, validation, intended prompt/actions, and gated actions.
- [ ] Kimi CLI capabilities are inspected without exposing secrets or performing development work during inspection.
- [ ] No unsupported Kimi invocation flags are invented.
- [ ] No autonomous commit, push, merge, reset, force, deployment, secrets access, or destructive database command is implemented.
- [ ] Automated tests cover the core policy gates.
- [ ] Existing pytest suite remains passing.
- [ ] `docs/architecture/AGENT_RUNNER.md` documents architecture, state flow, threat/safety boundaries, and future extension points.
- [ ] An ADR records the fail-closed permission model and replaceable worker-adapter decision.
- [ ] No ERP/business functionality or schema is changed.
- [ ] Completion report is produced.

## Test requirements
At minimum add deterministic tests for:

1. **Task parsing**
   - READY task is parsed correctly.
   - Missing/unknown status fails safely.

2. **Task status gate**
   - READY accepted.
   - REWORK accepted.
   - DRAFT rejected.
   - REVIEW rejected.
   - APPROVED rejected for execution.
   - BLOCKED rejected.

3. **Branch gate**
   - `agent-control-foundation` or another non-main task branch can pass.
   - `main` fails.

4. **Working-tree gate**
   - clean tree passes.
   - dirty tree fails.

5. **Prompt generation**
   - generated instruction references `AGENTS.md` and exactly one selected task path.
   - instruction contains the no-commit/no-push approval gate.
   - full task specification is not redundantly embedded.

6. **Dry-run safety**
   - worker subprocess is not launched in default/dry-run mode.
   - no Git mutation command is executed.

7. **Worker adapter boundary**
   - fake adapter can be used in tests without Kimi installed/running.
   - worker failure/unsupported invocation is represented as a controlled result rather than causing uncontrolled follow-on actions.

Run the full test suite with:

```bash
.venv/bin/python -m pytest tests/ -v
```

Also run import/CLI sanity checks for the runner.

## Constraints
- Read and obey `AGENTS.md` first.
- Stay on `agent-control-foundation`.
- Do not modify `main`.
- Do not merge anything.
- Do not commit or push implementation until owner/reviewer authorises the exact TASK-005 changes for review.
- Do not inspect or expose `.env` contents.
- Do not add credentials, tokens, API keys, or GitHub/Kimi secrets to configuration files.
- Prefer Python standard library and existing project dependencies; add a dependency only if clearly necessary and justify it in the completion report.
- Prefer subprocess argument arrays rather than shell-string execution where commands are necessary.
- Avoid `shell=True` unless a verified unavoidable requirement exists; if so, stop and report for review before implementation.
- Never execute task-file text as shell commands.
- Treat task files as instructions/metadata, not executable code.
- Keep the first version local, explicit, and understandable.
- Do not build a general autonomous computer-control agent.

## Owner/reviewer gates
The first runner foundation may automatically perform only low-risk inspection/planning actions such as:
- reading approved repository files,
- parsing task metadata,
- `git status` / branch inspection,
- generating a worker prompt,
- running its own isolated automated tests when explicitly invoked during development.

The following remain gated and must **not** become autonomous in TASK-005:
- committing,
- pushing,
- merging,
- deployment,
- production/database destructive actions,
- secret access,
- destructive Git actions,
- commercial/compliance/business-rule changes.

## Decisions required
None required to begin.

If Kimi CLI cannot be invoked safely/non-interactively using documented local capabilities, implement the worker-adapter boundary and dry-run behavior only, then report the limitation for the next controlled decision.

## Completion report
### Implemented

### Files changed

### Git / repository behavior

### Database changes

### Tests and results

### Kimi CLI capability findings

### Allowed automatic actions

### Gated actions

### Assumptions

### Risks / unresolved issues

### Decisions required

### Recommended next step
