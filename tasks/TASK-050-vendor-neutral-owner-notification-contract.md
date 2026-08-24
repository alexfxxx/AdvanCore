# TASK-050 — Vendor-Neutral Owner Notification Contract

STATUS: REVIEW

## Objective

Produce a stable, redacted notification view from the authoritative exception
inbox so Codex desktop or another approved client can notify the owner without
duplicating governance or receiving raw evidence.

## In scope

- Map validated inbox entries to bounded notification IDs, severity, title,
  message and owner-decision flag.
- Exclude commands, evidence paths, prompts, transcripts, credentials,
  environment, source contents and mutation actions.
- Provide deterministic ordering, deduplication IDs and stable JSON.
- Add tests and a delivery-boundary runbook.

## Out of scope

Sending messages, polling, background services, vendor APIs, authentication,
applying decisions, merge, `main`, deployment, or credentials.

## Allowed changed-file scope

- `tasks/TASK-050-vendor-neutral-owner-notification-contract.md`
- `advancore/agent_runner/owner_notifications.py`
- `advancore/agent_runner/__init__.py`
- `tests/test_owner_notifications.py`
- `docs/runbooks/OWNER_NOTIFICATIONS.md`

## Owner decisions

None for the permanent contract. Creating a Codex scheduled delivery remains a
manual editor handoff for the owner's return.

## Completion report

### Implemented

- Added a stable, provider-neutral notification projection over TASK-027.
- Added deterministic deduplication identifiers and bounded content.
- Excluded all commands, evidence references and raw/sensitive fields.
- Repaired independent review by whitelisting task/run identifiers and replacing
  all inbox-supplied titles/reasons with controlled notification templates.

### Database changes

None.

### Tests executed and results

- Focused notification and validated-inbox suites after repair: 30 passed.
- Python compile and `git diff --check`: passed.

### Decisions required

- The owner must approve/open the local scheduled-delivery editor after return.
