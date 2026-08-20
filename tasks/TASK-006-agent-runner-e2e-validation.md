# TASK-006 — Agent Runner End-to-End Validation

STATUS: READY

## Purpose

Prove the TASK-005 Local Agent Runner can safely launch Kimi for one bounded task and return to the human/reviewer approval gate without committing, pushing, merging, or expanding scope.

This is a validation task, not a product-feature task.

## Facts

- TASK-005 established a fail-closed local Agent Runner.
- The runner is dry-run by default.
- Kimi execution requires explicit `--execute --worker kimi`.
- Commit, push, merge, destructive Git operations, production/destructive database actions, secret access, compliance/commercial changes, and autonomous approval remain gated.

## Required implementation

1. Create `docs/validation/AGENT_RUNNER_E2E.md`.
2. The document must record this supervised validation run and contain these sections:
   - Purpose
   - Preconditions
   - Runner invocation
   - Worker boundary
   - Validation result
   - Safety observations
   - Facts
   - Assumptions
   - Risks / unresolved issues
   - Recommended next step
3. Add `tests/test_agent_runner_e2e_artifact.py` with small deterministic tests that verify the validation document exists and contains the required headings.
4. Run the full pytest suite.
5. Fill in the Completion report in this task file.
6. Stop with completion report and `git status --short`.

## Execution constraints

- Do not modify Agent Runner implementation code during TASK-006.
- Do not modify database models, migrations, database configuration, ERP modules, or production code.
- Do not access secrets or credentials.
- Do not perform network, production, deployment, or destructive actions.
- Do not commit or push.
- Do not merge or modify `main`.
- Do not create another task.
- Do not broaden this into an Agent Runner redesign.

## Acceptance criteria

- `docs/validation/AGENT_RUNNER_E2E.md` exists with all required sections.
- `tests/test_agent_runner_e2e_artifact.py` exists and passes.
- Full existing test suite passes.
- No Agent Runner implementation code changed.
- No database/model/migration files changed.
- No commit or push occurred.
- Worker stops at the human/reviewer approval gate.

## Reasoning labels

### FACT

TASK-006 is deliberately low-impact so the orchestration path itself, rather than feature complexity, is what is being tested.

### ASSUMPTION

The locally installed Kimi CLI continues to support the bounded `--prompt` invocation validated in TASK-005.

### INFERENCE

If this task completes through the Agent Runner without manual prompt transfer into Kimi, the first part of the Alex-to-Kimi relay has been successfully automated.

### PROPOSAL

After successful independent review, use the evidence from TASK-006 to define the next runner hardening step rather than immediately granting broader autonomy.

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
