# TASK-032 — Correct terminal publication classification in the orchestration inbox

STATUS: READY

## Objective

Ensure the read-only orchestration inbox excludes successfully published terminal runs only after validating their immutable task, review, decision, and finalization evidence chain, without treating later feature-line repository changes as stale evidence.

## Business context

The exception inbox currently produces false exceptions for completed publication runs because it applies current repository HEAD and working-path fingerprint checks to historical terminal checkpoints and does not accept the finalization boundary's directory-form artifact reference. Correct classification will keep the inbox operationally useful while preserving fail-closed visibility for genuinely incomplete, malformed, conflicting, or failed runs.

## Facts

- AGENTS.md defines GitHub as the source of truth for code and approved knowledge.
- The orchestration inbox is a read-only projection and must not normalize, reconcile, or mutate checkpoint or evidence state.
- Existing inbox validation compares checkpoint HEAD and path fingerprints with current repository state before excluding a terminal PUBLISHED checkpoint.
- Later authorized commits or working-tree changes on the same feature line do not invalidate an already completed publication outcome.
- The finalization boundary uses the canonical append-only artifact named .agent_runner/finalize/finalize.jsonl.
- Existing orchestration finalization handling accepts a recorded finalization artifact directory by resolving its finalize.jsonl child.
- Terminal publication evidence must remain bound to one authoritative task, review bundle, approving controller decision, and successful finalization record.
- TASK-029, TASK-030, and TASK-031 provide historical checkpoint and finalization shapes that require deterministic regression coverage.

## Assumptions

- Existing task, review-bundle, controller-decision, and finalization parsers or narrowly reusable validation helpers provide enough information to validate the terminal evidence chain without introducing a new persistence mechanism.
- A successful terminal finalization record has a recognized successful publication outcome and contains immutable references sufficient to bind the task, review bundle, controller decision, feature line, and finalized commit.
- Current HEAD and current working-path fingerprints remain relevant stale-evidence checks for unresolved checkpoints but are not authoritative validity checks for an otherwise fully validated terminal publication.
- The correction can be implemented entirely through read-only local filesystem and Git-object inspection without network access.

## In scope

- Separate terminal PUBLISHED checkpoint validation from unresolved-checkpoint freshness validation so later current-HEAD or working-path changes do not create false terminal exceptions.
- Accept the finalization boundary's existing artifact-directory representation by resolving only its canonical finalize.jsonl child.
- Validate the authoritative task identity and task-file linkage for a terminal checkpoint.
- Resolve and validate the exact linked review bundle, authorized APPROVE controller decision, and successful finalization record.
- Validate immutable linkage among the checkpoint, task, review bundle, controller decision, finalization record, feature line, review or finalized commit identities, and recorded terminal outcome.
- Require terminal checkpoint fields and completed-phase evidence to be internally consistent with the validated finalization outcome.
- Exclude a valid, fully linked terminal published run from the unresolved inbox.
- Keep incomplete, malformed, missing, ambiguous, duplicated, conflicting, stale unresolved, unsuccessful-finalization, and failed runs visible with deterministic fail-closed classifications and reasons.
- Preserve current freshness checks for non-terminal or unresolved checkpoints.
- Add deterministic regression fixtures representing relevant TASK-029, TASK-030, and TASK-031 checkpoint and finalization artifact shapes.
- Update narrowly relevant architecture documentation to describe terminal evidence validation and the distinction between immutable publication evidence and mutable current repository state.

## Explicitly out of scope

- Automatic or explicit completed-run reconciliation.
- Creating, editing, normalizing, replacing, or deleting orchestration checkpoints or evidence artifacts.
- Inferring successful publication from checkpoint flags alone.
- Weakening validation for missing, malformed, ambiguous, conflicting, duplicated, incomplete, or unsuccessful terminal evidence.
- Changing ordinary orchestration resume behavior or unresolved-checkpoint stale-evidence protections.
- Creating or changing controller decisions, task authority, review outcomes, or publication authority.
- Running or repeating finalization or publication.
- Staging, committing, pushing, fetching, merging, tagging, releasing, deploying, switching lines, resetting, rebasing, force-pushing, or rewriting history.
- Changing main or any protected integration line.
- Accessing credentials, secrets, tokens, network services, production data, or live remotes.
- Database schema changes, migrations, operational-data changes, commercial-rule changes, or Singapore compliance-rule changes.
- Broad redesign of orchestration, reconciliation, lifecycle, controller, review, or finalization components.

## Allowed changed-file scope

- `advancore/agent_runner/orchestration_inbox.py`
- `tests/test_orchestration_inbox.py`
- `docs/decisions/ADR-027-read-only-orchestration-exception-inbox.md`
- `docs/architecture/AGENT_RUNNER.md`
- `tasks/TASK-032-correct-terminal-publication-classification-in-the.md`

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

- A terminal checkpoint with internally consistent PUBLISHED phase and outcome, verified publication fields, required completed phases, and one fully valid immutable evidence chain is absent from the unresolved inbox.
- A fully validated historical terminal publication remains absent when current HEAD advances through later feature-line commits.
- A fully validated historical terminal publication remains absent when current working-path fingerprints differ from those recorded at completion.
- A finalization_artifact_path referring to the established finalization artifact directory resolves specifically to its canonical finalize.jsonl file.
- A finalization artifact reference to a directory without canonical finalize.jsonl evidence remains visible as invalid evidence.
- Terminal validation resolves exactly one successful finalization record and verifies its task, task filename where represented, feature line, review bundle, controller decision, review or finalized commit identities, and successful outcome against checkpoint evidence.
- The linked controller decision must be an authorized APPROVE decision and must match the exact task and review bundle.
- Missing, malformed, unsafe, symlinked, ambiguous, duplicated, conflicting, incomplete, or unsuccessful evidence never causes a run to be silently excluded.
- Failed and genuinely unresolved runs remain visible under their existing fail-closed classifications.
- Non-terminal checkpoints continue to be classified stale when their required current HEAD, feature-line, or path-fingerprint evidence differs.
- Inbox API and CLI execution remain byte-for-byte read-only with respect to repository content, Git state, checkpoints, and evidence.
- Inbox ordering and serialized output remain deterministic.
- No network, credential, remote mutation, publication, reconciliation, or protected-line operation is introduced.

## Test requirements

- Add a deterministic TASK-029-shaped regression showing that a successful historical publication is excluded despite later current-HEAD and path-fingerprint changes.
- Add a deterministic TASK-030-shaped regression covering a terminal checkpoint whose finalization reference identifies the established artifact directory and resolves to finalize.jsonl.
- Add a deterministic TASK-031-shaped regression covering a valid historical finalized commit behind a later synchronized feature-line tip without reclassifying the terminal run as stale.
- Add negative cases for missing canonical finalize.jsonl, malformed JSONL records, no matching record, multiple matching records, unsuccessful outcomes, conflicting task identity, conflicting task filename, conflicting feature line, conflicting commit identity, conflicting review-bundle reference, and conflicting controller-decision reference.
- Add negative cases for a non-APPROVE decision, an unauthorized decision actor, unsafe paths, directory misuse, and symlink evidence.
- Assert that incomplete PUBLISHED checkpoints and failed runs remain visible.
- Assert that unresolved checkpoints retain current HEAD and path-fingerprint stale detection.
- Retain or extend the repository snapshot test proving both API and CLI inbox operations make no filesystem or Git-state changes.
- Run tests/test_orchestration_inbox.py.
- Run relevant orchestration, completed-run reconciliation, controller-decision, review-bundle, and finalization regression tests.
- Run the complete test suite because production runner validation logic changes.

## Constraints

- Keep the inbox strictly read-only and side-effect free.
- Validate terminal evidence before applying mutable current-repository freshness checks.
- Treat historical completion as valid only from one complete and internally consistent immutable evidence chain; checkpoint flags alone are insufficient.
- Resolve a directory-form finalization reference only to the exact canonical finalize.jsonl filename and reject alternative inferred files.
- Reject evidence paths that escape the repository, are symlinks, are missing, or are not of the expected file or canonical-directory form.
- Unknown, malformed, incomplete, duplicated, ambiguous, unsuccessful, or conflicting evidence must fail closed and remain visible.
- Do not auto-reconcile, mutate checkpoints, create decisions, approve work, or publish.
- Do not stage, commit, push, fetch, merge, tag, release, deploy, switch lines, reset, rebase, force-push, rewrite history, or touch main.
- Do not access credentials, secrets, tokens, network services, live remotes, or production data.
- Preserve existing working functionality and use the smallest reversible correction within the listed files.
- Do not introduce database, migration, commercial, customer-specific, or compliance changes.
- Maintain explicit FACT, ASSUMPTION, INFERENCE, and PROPOSAL distinctions in any material documentation changes.
- The eventual completion report must include implemented work, files changed, database impact, tests and results, assumptions, risks, unresolved issues, decisions required, and the recommended next step.

## Owner decisions

None.

## Completion report

### Implemented

### Files changed

### Database changes

### Tests executed and results

### Assumptions

### Risks / unresolved issues

### Decisions required

### Recommended next step
