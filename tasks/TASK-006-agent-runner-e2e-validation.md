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

### Implemented

- Created `docs/validation/AGENT_RUNNER_E2E.md` recording the supervised TASK-006
  validation run with all required sections.
- Added `tests/test_agent_runner_e2e_artifact.py` with deterministic tests that
  verify the validation document exists and contains the required headings.
- Ran the local Agent Runner in dry-run/planning mode for TASK-006 to confirm
  task discovery, safety validation, and canonical worker instruction generation.
- Observed the runner fail closed when the working tree became dirty after
  creating the new validation files.
- Executed TASK-006 under direct operator supervision; the worker stopped at the
  human/reviewer approval gate without committing, pushing, merging, or
  performing destructive actions.

### Files changed

- `docs/validation/AGENT_RUNNER_E2E.md` (new)
- `tests/test_agent_runner_e2e_artifact.py` (new)
- `tasks/TASK-006-agent-runner-e2e-validation.md` (completion report section only)

No Agent Runner implementation code was modified.
No database models, migrations, ERP modules, or production code were modified.

### Database changes

None. No model changes or Alembic revisions were introduced.

### Tests executed and results

```bash
.venv/bin/python -m pytest tests/ -v
```

Result: **63 passed** (61 pre-existing + 2 new E2E artifact tests).

### Assumptions

- The locally installed Kimi Code CLI continues to support the bounded
  `--prompt` invocation validated in TASK-005.
- The operator launching `--execute --worker kimi` supervises the run and
  reviews the worker output before approving any commit or push.

### Risks / unresolved issues

- The runner's safety depends on the worker honoring the no-commit/no-push
  instruction. A future task may add an explicit pre- or post-execution Git-state
  verification step.
- Worker execution is local and interactive-terminal dependent. Long-running or
  multi-turn worker sessions are not yet addressed.
- No audit log of runner invocations exists outside the terminal output.
- The `IN_PROGRESS` task status is parsed but not executable; the runner does
  not currently update task status itself.
- This validation did not execute `--execute --worker kimi` because doing so
  would recursively spawn a Kimi process with the same TASK-006 prompt.

### Decisions required

None required to complete TASK-006.

Optional future decisions:

- Whether to perform a supervised `--execute --worker kimi` run using a
  non-recursive task payload.
- Whether to add a post-worker Git-state verification step before owner review.
- Whether to add an explicit task-status transition helper behind its own
  approval gate.

### Recommended next step

1. Independent review of TASK-006 changes on `agent-control-foundation`.
2. After approval, a controlled commit/push (still human-gated) of the validation
   artifact and test.
3. Use the evidence from this validation to define the next runner hardening
   step rather than immediately granting broader autonomy.

### `git status --short`

```text
?? docs/validation/
?? tests/test_agent_runner_e2e_artifact.py
```
