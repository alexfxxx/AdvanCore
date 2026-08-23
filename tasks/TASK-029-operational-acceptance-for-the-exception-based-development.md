# TASK-029 — Operational Acceptance for the Exception-Based Development Loop

STATUS: READY

## Objective

Provide deterministic end-to-end acceptance coverage and an operator runbook demonstrating that the governed AdvanCore development loop can progress through planner fallback, runner-owned task drafting, explicit owner resumptions, bounded implementation and verification, and controlled feature-branch finalization delegation without live publication.

## Business context

The existing orchestration capabilities need a single operational proof that their exception-based control points work together, preserve owner authority, and fail safely. This closes the validation gap between individually tested components and the complete governed development loop while keeping GitHub as the source of truth and preventing workers from approving or publishing their own work.

## Facts

- AGENTS.md defines GitHub as the source of truth for code, schema, migrations, tests, architecture decisions, and approved knowledge.
- The agent_runner is the authoritative orchestration boundary.
- Workers are limited to planning proposals or bounded implementation work and cannot approve their own critical work.
- The target flow requires an explicit Kimi-Swarm planning attempt with Codex planner fallback.
- Task draft construction must be owned by the runner.
- Task execution and implementation finalization require separate explicit owner decisions.
- Automated acceptance must use temporary repositories and controlled fakes.
- Automated tests must not perform live publication.
- Production code changes are permitted only when acceptance testing exposes a specific defect.

## Assumptions

- Existing planner fallback, owner-decision intake, lifecycle bridge, verification, and finalization boundaries can be composed without architectural redesign.
- Controlled worker, controller, transport, and publication fakes can exercise the full flow deterministically without credentials or network access.
- Feature-branch finalization delegation can be proven through recorded intent or a controlled fake without modifying main or invoking a live remote.
- The existing task and controller decision representations provide sufficient evidence for asserting runner ownership and explicit resumptions.

## In scope

- Add deterministic end-to-end acceptance coverage for the complete exception-based development loop.
- Simulate a Kimi-Swarm planning failure or unavailable result and verify explicit fallback to the Codex planner.
- Verify that planner output remains a proposal and that the runner constructs the canonical DRAFT task representation.
- Verify that execution pauses until an explicit owner task decision is received and then resumes through the established decision-intake boundary.
- Execute a bounded Codex implementation worker through a controlled fake and verify that its authority is implementation-only.
- Verify runner-controlled post-worker validation and preservation of auditable evidence.
- Verify that the flow pauses again until an explicit owner implementation decision is received.
- Verify controlled delegation of feature-branch finalization after the second explicit owner decision.
- Add an operator runbook describing prerequisites, commands, expected checkpoints, evidence, failure handling, and safe resume procedures.
- Make the smallest production-code correction necessary only if the new acceptance coverage demonstrates a specific defect.
- Reproduce and correct the approved-DRAFT clean-tree handoff: after explicit
  task approval, ensure the runner can preserve the task specification as
  GitHub source-of-truth and reach clean worker execution without an owner
  manually staging/committing/pushing the generated task.

## Explicitly out of scope

- Live publication or interaction with live remotes during automated tests.
- Changes to main or any equivalent protected integration line.
- Integrating or completing changes across repository lines.
- Production deployment or release activity.
- Credential, secret, token, or production-data access.
- Changing commercial, customer-specific, or Singapore compliance rules.
- Broad orchestration redesign or replacement of agent_runner authority.
- Allowing planners or implementation workers to construct authoritative task records, make controller decisions, approve their own work, or finalize autonomously.
- Database schema changes, migrations, or operational data changes.
- Rewriting existing migration or repository history.

## Allowed changed-file scope

- `tests/test_exception_development_loop_e2e.py`
- `docs/runbooks/EXCEPTION_DEVELOPMENT_LOOP.md`
- `advancore/agent_runner/auto_pipeline.py`
- `advancore/agent_runner/goal_task.py`
- `advancore/agent_runner/orchestration.py`
- `advancore/agent_runner/decision_lifecycle_bridge.py`
- `advancore/agent_runner/finalize.py`
- `tasks/TASK-029-operational-acceptance-for-the-exception-based-development.md`

## Database impact

None

## Safety requirements

- GitHub remains the source-of-truth.
- `main` remains untouched and non-executable unless explicitly approved.
- Worker/swarm cannot approve its own work.
- No automatic staging, commit, push, merge, tag, deploy, switch, reset,
  rebase, or history rewrite.
- This generated task is DRAFT and cannot execute until a valid
  `DRAFT -> READY` controller/owner transition.
- Unknown, unsafe, malformed, conflicting, or ambiguous states fail closed.
- The planner proposed only; the runner constructed this DRAFT; the
  controller/owner must authorize execution.

## Acceptance criteria

- A deterministic acceptance scenario starts from an owner goal and records a Kimi-Swarm planner attempt followed by Codex planner fallback under a controlled fallback condition.
- The scenario proves that planner output is non-authoritative and that agent_runner constructs the canonical DRAFT task representation.
- The scenario proves that no implementation worker runs before an explicit owner task decision is ingested through the established controller boundary.
- After the first explicit owner decision, exactly one bounded Codex implementation worker is invoked with only the authorised task scope.
- The scenario proves that implementation-worker output cannot alter controller decisions, self-authorize continuation, or directly invoke finalization.
- Runner-controlled verification executes after implementation and records deterministic success or failure evidence.
- The scenario proves that finalization delegation cannot occur before a separate explicit owner implementation decision.
- After the second explicit owner decision, agent_runner delegates only controlled feature-branch finalization and records the delegation outcome.
- The acceptance scenario asserts the ordering and identity of every major checkpoint, worker invocation, pause, resume, verification event, and finalization delegation.
- All external planner, worker, controller, transport, repository, and publication effects are represented by controlled fakes or temporary local repositories.
- The test fails if any live publication path, live remote mutation, protected integration-line mutation, deployment action, or credential lookup is attempted.
- Failure cases remain fail-closed and preserve enough evidence for an operator to identify the blocked checkpoint and safely resume through an explicit controller decision.
- The operator runbook documents the demonstrated happy path, planner fallback, both owner-decision checkpoints, verification evidence, controlled finalization delegation, common exceptions, and recovery steps.
- Any production-code change is tied to a reproducible defect exposed by the acceptance scenario and is covered by a focused regression assertion.
- The approved generated task specification is safely preserved on the current
  non-`main` feature branch through an existing or narrowly bounded governed
  publication boundary before clean-tree worker validation; `main`, merge,
  force-push, arbitrary staging, and implementation self-publication remain impossible.

## Test requirements

- Add a deterministic end-to-end acceptance test using an isolated temporary Git repository with no live remote.
- Use controlled fakes for Kimi-Swarm, Codex planner, Codex implementation worker, controller decision intake, verification, and finalization delegation.
- Assert Kimi-Swarm-to-Codex planner fallback reason, ordering, and audit evidence.
- Assert runner ownership of canonical task construction and rejection of worker-authored authoritative state.
- Assert both explicit owner-decision pauses and resumptions independently.
- Assert bounded Codex implementation invocation, supplied scope, invocation count, and absence of approval authority.
- Assert verification runs before the second owner-decision checkpoint and before finalization delegation.
- Assert finalization is delegated only to the controlled feature-branch boundary.
- Add negative-path coverage for missing owner decisions, worker failure, verification failure, malformed planner output, and attempted publication.
- Run the new acceptance test and all existing agent_runner, planner fallback, owner-decision, lifecycle, verification, and finalization tests.
- Run the complete test suite when production code changes are required.

## Constraints

- Keep agent_runner authoritative for orchestration, task construction, lifecycle enforcement, verification, and delegation.
- Keep GitHub repository content as the source of truth; do not use repository files as a production operational database.
- Treat all planner results as proposals and all implementation-worker results as bounded implementation output.
- Require explicit controller or owner decisions at both defined resume points.
- Use deterministic fakes and temporary repositories; do not require network connectivity.
- Do not access credentials, secrets, tokens, or production data.
- Do not perform live remote writes, protected integration-line changes, integration operations, deployment, release, tagging, or history rewriting.
- Ensure tests fail closed if an unexpected external side effect is requested.
- Preserve existing behavior and avoid broad refactoring.
- Limit production changes to the smallest reversible correction for a defect specifically reproduced by the new acceptance coverage.
- Maintain explicit FACT, ASSUMPTION, INFERENCE, and PROPOSAL distinctions in documentation where reasoning or governance conclusions are recorded.
- Document tests, assumptions, risks, unresolved issues, decisions required, and the recommended next step in the eventual completion report.

## Owner decisions

None.

Resolved before DRAFT approval:

- Controlled feature-branch finalization and recorded delegation evidence are
  sufficient automated operational proof; live publication remains prohibited
  in tests.
- A production correction is authorized only for a reproducible acceptance
  defect, only within the listed scope, and only after independent review.

## Completion report

### Implemented

### Files changed

### Database changes

### Tests executed and results

### Assumptions

### Risks / unresolved issues

### Decisions required

### Recommended next step
