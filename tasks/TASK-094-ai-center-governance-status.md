# TASK-094 — AI Center Governance Status

STATUS: REVIEW

## Objective

Show the read-only implementation route preview and deterministic offline
multi-worker governance rehearsal in AI Center.

## Business context

The owner should see whether Kimi is currently proven selectable and whether
the permanent routing safeguards still pass, without watching terminal output
or starting a worker.

## In scope

- Show selected or blocked implementation-route preview from local evidence.
- Show bounded evidence states and explain Codex launch-time checking.
- Run the offline nine-scenario governance rehearsal during page rendering.
- Show pass/fail and zero-worker-launch truthfully alongside the exception inbox.

## Out of scope

Worker launch, authority consumption, provider probing, Gemini activation or
authentication, credentials, database mutation, deployment, or `main`.

## Allowed changed-file scope

- `tasks/TASK-094-ai-center-governance-status.md`
- `advancore/pages/ai_center.py`
- `tests/test_ai_center_page.py`

## Database impact

None.

## Acceptance criteria

- [x] All-clear inbox no longer hides worker governance status.
- [x] Preview shows selected or blocked without inferring Codex availability.
- [x] Offline rehearsal reports zero launches.
- [x] Exceptions and source errors expose no local details.
- [x] Focused tests and `git diff --check` pass.
- [x] Completion report produced.

## Constraints

AI Center remains read-only and cannot approve, activate, or execute a worker.

## Owner decisions

None.

## Completion report

### Implemented

AI Center routing preview, bounded evidence, and offline governance self-check.

### Files changed

Task record, AI Center page, and focused page tests.

### Database changes

None.

### Tests and results

AI Center, preview, evidence, and rehearsal tests pass; `git diff --check`
passes.

### Assumptions

Page rendering may safely run the deterministic no-process rehearsal.

### Risks / unresolved issues

Codex status remains a launch-time fact, so blocked preview does not mean the
fallback will necessarily fail when invoked.

### Decisions required

None.

### Recommended next step

Add the Gemini pre-authentication readiness gate in TASK-095.
