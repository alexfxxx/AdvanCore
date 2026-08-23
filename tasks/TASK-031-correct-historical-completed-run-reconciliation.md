# TASK-031 — Correct historical completed-run reconciliation

STATUS: READY

## Objective

Allow explicit completed-run reconciliation to recognize one authoritative historical PUSHED finalization when an interrupted checkpoint lacks later evidence paths, while preserving fail-closed validation and permitting later authorized feature-line commits.

## Business context

Real historical runs may have completed publication before their orchestration checkpoints persisted review, decision, or finalization paths. The recovery boundary must recognize that existing outcome without repeating publication, inventing authority, rejecting valid later feature-line work, or weakening ordinary stale-evidence protections.

## Facts

- AGENTS.md defines GitHub as the source of truth for code and approved knowledge.
- The runner already provides an explicit completed-run reconciliation boundary with preview and apply modes.
- Existing reconciliation requires synchronized local and locally recorded origin-tracking tips for a named non-main line.
- Existing reconciliation validates canonical review, controller-decision, and finalization evidence.
- A real interrupted checkpoint may lack review_bundle_path, decision_path, and finalization_artifact_path even though canonical evidence records were subsequently written.
- A valid historical finalized commit may be behind the current synchronized feature-line tip when later authorized work has been added.
- TASK-029 provides the historical exception-based development flow that must be represented by regression coverage.
- The requested correction must not alter ordinary orchestration stale-evidence behavior.

## Assumptions

- Canonical PUSHED finalization records contain sufficient task identity, task filename, feature-line name, finalized commit, review-bundle reference, and controller-decision reference to resolve and validate their complete evidence chain.
- Canonical evidence locations and existing parsers can be reused without introducing a new storage subsystem.
- Commit ancestry can be checked entirely from existing local Git objects and references without contacting origin.
- The current preview interface can report the resolved evidence chain without persisting checkpoint or evidence changes.

## In scope

- Correct explicit completed-run reconciliation for an interrupted checkpoint that does not contain later review, decision, or finalization paths.
- Resolve exactly one canonical finalization record whose outcome is PUSHED and whose task identity, task filename, and named non-main feature line match the checkpoint and current repository facts.
- Use the resolved finalization record to locate its exact linked review bundle and controller decision within their canonical evidence locations.
- Validate the complete linkage among the checkpoint task, task filename, feature line, finalization record, review bundle, and controller decision.
- Require the linked controller decision to contain an APPROVE value from an already authorized owner or controller actor.
- Require the current local feature-line tip to equal its existing local origin-tracking tip.
- Require the finalized commit identified by the resolved finalization record to be an ancestor of the current synchronized tip, allowing later commits on the same feature line.
- Retain strict validation of checkpoint evidence paths when any such paths are present.
- Reject missing, malformed, duplicated, ambiguous, conflicting, mismatched, or non-ancestor evidence before mutation.
- Keep preview read-only and preserve ordinary stale-evidence checks and automatic-orchestration behavior.
- Add deterministic regression coverage representing the real TASK-029 historical evidence shape.
- Update narrowly relevant runner documentation to explain historical evidence discovery, ancestry validation, and fail-closed behavior.

## Explicitly out of scope

- Automatic reconciliation during ordinary orchestration or stale-evidence handling.
- Creating, modifying, replacing, or inferring review, controller-decision, or finalization evidence.
- Inferring authorization from worker success, verification success, checkpoint state, Git ancestry, or publication output.
- Relaxing actor authorization, APPROVE validation, exact evidence linkage, canonical-location checks, or ambiguity rejection.
- Fetching from or otherwise contacting origin.
- Publishing, integrating, releasing, or deploying changes.
- Staging files, switching repository lines, changing HEAD, modifying remotes, tagging, resetting, rebasing, force-updating, or rewriting history.
- Touching main or any equivalent protected integration line.
- Broad redesign of orchestration, lifecycle, review, controller-decision, finalization, or audit architecture.
- Database schema, migration, operational-data, production-data, commercial-rule, or compliance-rule changes.
- Credential, secret, or token access.

## Allowed changed-file scope

- `advancore/agent_runner/orchestration.py`
- `tests/test_orchestration.py`
- `tests/test_exception_development_loop_e2e.py`
- `docs/architecture/AGENT_RUNNER.md`
- `docs/runbooks/EXCEPTION_DEVELOPMENT_LOOP.md`
- `tasks/TASK-031-correct-historical-completed-run-reconciliation.md`

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

- Reconciliation can validate an eligible interrupted checkpoint when review_bundle_path, decision_path, and finalization_artifact_path are absent.
- Evidence discovery begins from exactly one canonical PUSHED finalization record matching the checkpoint task identity, exact task filename, and current named non-main feature line.
- The resolved finalization record's exact review-bundle reference resolves to one valid bundle in the canonical review location, and all task, filename, feature-line, and relevant Git identities match.
- The resolved finalization record's exact controller-decision reference resolves to one valid decision in the canonical decision location, with an APPROVE value, an authorized owner or controller actor, and exact linkage to the resolved review bundle.
- Any checkpoint review, decision, or finalization reference that is present must match the independently resolved canonical evidence exactly; conflicting persisted references fail closed.
- The current local feature-line tip and existing local origin-tracking tip must be identical.
- The finalized commit must exist locally and be an ancestor of the current synchronized tip; equality remains valid, and a finalized commit followed by later feature-line commits is accepted.
- A finalized commit that is not an ancestor of the current synchronized tip is rejected.
- Zero matches, multiple matching finalization records, duplicate or ambiguous linked evidence, malformed records, missing referenced files, unauthorized actors, non-APPROVE decisions, linkage mismatches, and conflicting commit identities are rejected before mutation.
- Preview performs the full validation and reports the proposed recognition without changing the checkpoint, evidence files, working tree, index, references, HEAD, or repository-line state.
- A successful applied reconciliation records the historical finalized commit separately from the current synchronized tip where necessary and transitions only the eligible checkpoint to the already-proven terminal outcome.
- Failed reconciliation preserves the checkpoint and all existing evidence byte-for-byte.
- Ordinary resume and stale-evidence validation remain unchanged and never invoke historical reconciliation implicitly.
- No network operation, worker execution, finalization rerun, publication operation, integration operation, release operation, deployment operation, or protected-line mutation occurs.

## Test requirements

- Add a deterministic success regression modeled on the TASK-029 historical flow with an interrupted checkpoint lacking review, decision, and finalization paths; one canonical PUSHED finalization; its exact linked review bundle; its exact authorized APPROVE decision; and synchronized local origin-tracking state.
- In that regression, add at least one later authorized commit on the same feature line and prove reconciliation succeeds because the historical finalized commit is an ancestor of the current synchronized tip.
- Verify preview leaves the checkpoint, canonical evidence, working tree, index, local references, and HEAD unchanged byte-for-byte where applicable.
- Verify applied reconciliation mutates only the intended checkpoint and preserves all canonical review, decision, finalization, and audit evidence.
- Add negative coverage for no matching finalization, malformed finalization, duplicate matching finalizations, conflicting finalization fields, missing linked review bundle, malformed linked review bundle, review-link mismatch, missing linked decision, malformed linked decision, duplicate or ambiguous decision evidence, unauthorized actor, non-APPROVE value, decision-link mismatch, missing finalized commit, and non-ancestor finalized commit.
- Add negative coverage for main, detached HEAD, feature-line mismatch, missing origin-tracking reference, and unequal local and origin-tracking tips.
- Add coverage proving a present checkpoint evidence path must exactly match the independently resolved canonical path and that a conflicting path is rejected.
- For each rejected case, assert a non-zero or raised fail-closed result and preservation of the checkpoint and existing evidence.
- Retain or extend CLI coverage proving preview remains the default read-only behavior and the explicit apply path is required for checkpoint mutation.
- Run tests/test_orchestration.py and tests/test_exception_development_loop_e2e.py.
- Run the complete test suite because the correction affects shared orchestration recovery behavior.

## Constraints

- Treat reconciliation only as recognition of authority and publication evidence that already exist.
- Resolve evidence exclusively from canonical local evidence locations and validate referenced paths against repository-boundary and symbolic-link protections.
- Do not use latest-record fallback or select among multiple plausible records; every ambiguous state must fail closed.
- Validate all evidence and Git conditions before performing any mutation.
- Use only existing local Git objects and references; do not fetch or access remote credentials.
- Do not weaken, bypass, reorder, or reuse ordinary stale-evidence checks as part of the explicit recovery path.
- Do not infer or synthesize controller authority, and do not permit a worker or swarm to authorize its own work.
- Do not rerun finalization or perform any publication, integration, release, or deployment action.
- Do not stage files, alter the index, switch repository lines, change HEAD, modify remotes, touch main, reset, rebase, force-update, tag, or rewrite history.
- Preserve existing task, checkpoint, review, controller-decision, finalization, and audit evidence except for the smallest atomic checkpoint update after successful validation.
- Keep the implementation small, reversible, deterministic, and confined to the allowed changed-file scope.
- Do not access credentials, secrets, tokens, network services, production systems, or production data.
- Any eventual completion report must distinguish facts, assumptions, inferences, and proposals and report implemented work, files changed, database impact, tests, risks, unresolved issues, decisions required, and a recommended next step.

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
