# TASK-046 — Bounded Unattended Review and Repair Loop

STATUS: REVIEW

## Objective

Automatically repeat independent review and clear in-scope repair without
asking the owner after every finding, while stopping at a fixed budget or any
manual authority boundary.

## In scope

- Add a provider-neutral controller loop with injected review and repair
  boundaries; no Bugbot, Codex, Kimi, or vendor API dependency in AdvanCore.
- Consume TASK-045 routine authority before every review and repair.
- Allow at most three repair cycles and require a fresh independent review after
  every repair.
- Persist no raw findings, prompts, transcripts, credentials, or environment.
- Return concise clean, exhausted, blocked, or failed results suitable for the
  existing exception inbox/notification layer.
- Add deterministic tests and operating documentation.

## Out of scope

- Task/implementation approval, merge, `main`, deployment, production,
  credentials, destructive actions, or AI-generated authority.
- Automatically deciding that an ambiguous or out-of-scope finding is repairable.

## Allowed changed-file scope

- `tasks/TASK-046-bounded-unattended-review-repair-loop.md`
- `advancore/agent_runner/unattended_review.py`
- `advancore/agent_runner/__init__.py`
- `tests/test_unattended_review.py`
- `docs/runbooks/UNATTENDED_REVIEW.md`

## Acceptance criteria

- Clean first review stops without repair.
- Repairable findings run bounded repair followed by review until clean.
- Exhaustion, reviewer failure, repair failure, malformed results and standing
  authority failure stop without approval/publication.
- Manual-only actions are never represented by this loop.

## Owner decisions

None. The owner explicitly approved automatic bounded review and repair for the
next ten tasks while leaving manual approvals for their return.

## Completion report

### Implemented

- Added a provider-neutral, maximum-three-cycle independent review/repair loop.
- Required exact routine authority before every review and every repair.
- Required fresh independent review after repair and stopped safely on
  exhaustion, non-repairable findings, malformed evidence, failures or missing
  authority.
- Kept clean review as evidence requiring later manual implementation approval.
- Repaired independent review by strictly validating every callback field and
  keeping all validation/summary normalization inside the controlled reviewer
  or repair failure boundary.

### Files changed

- `tasks/TASK-046-bounded-unattended-review-repair-loop.md`
- `advancore/agent_runner/unattended_review.py`
- `advancore/agent_runner/__init__.py`
- `tests/test_unattended_review.py`
- `docs/runbooks/UNATTENDED_REVIEW.md`

### Database changes

None.

### Tests executed and results

- Focused standing-authority plus unattended-review suites: 23 passed.
- Python compile and `git diff --check`: passed.

### Decisions required

- Independent review and implementation approval remain manual.

### Recommended next step

- Add the approved Kimi-first worker routing integration in TASK-047.
