# ADR-027 — Read-Only Orchestration Exception Inbox

STATUS: ACCEPTED

Date: 2026-08-23

## Context

Versioned orchestration checkpoints already retain the bounded state needed to
identify pauses and failures. Operators nevertheless had to discover a run ID
and interpret checkpoint/report state manually. Moving that interpretation
into a desktop or phone client would duplicate governance logic and couple
AdvanCore to a presentation vendor.

## Decision

Add a provider-neutral, read-only exception projection owned by AdvanCore. It
discovers local checkpoint candidates and revalidates checkpoint schema,
authoritative task linkage, bounded artifact paths and correlations, Git
branch/HEAD/path evidence, and verified terminal publication state.

Classify retained entries as `action-required`, `operator-investigation`, or
`stale-or-invalid-evidence`. Sort them deterministically by classification
urgency, checkpoint timestamp, and run ID. Exclude only a fully revalidated,
idempotent `PUBLISHED` checkpoint. Surface unreadable, malformed, unsafe,
conflicting, missing, or stale evidence as a bounded invalid entry.

Expose the projection through `orchestration-inbox [--json] [--run <id>]`.
Each entry contains only bounded identity, state, reason, evidence references,
an owner-decision-required flag, and one exact non-applying resume preview
command. The JSON contract is versioned as
`advancore-orchestration-inbox-v1`.

The projection may call only existing read-only filesystem and Git inspection.
It must not normalize or write checkpoints, append audit, mutate lifecycle,
create or apply decisions, dispatch workers, resume orchestration, or perform
publication. Classification and presentation create no authority.

## Consequences

- Operators can discover all unresolved local runs without knowing an ID.
- Invalid evidence remains visible and fail closed.
- Codex desktop, phone views, and other clients can render the stable JSON but
  remain optional couriers rather than governance authorities.
- No notification, polling, server, remote API, credential, or production-data
  dependency is introduced.
- A preview command still requires explicit owner/controller action and
  `--apply` through existing governed paths before any mutation can occur.

## Verification

- `.venv/bin/python -m pytest tests/test_orchestration_inbox.py -v`
- `.venv/bin/python -m pytest tests/ -v`
- `git diff --check`
- Focused tests compare repository files, HEAD, and Git status byte-for-byte
  before and after API and CLI inspection.
