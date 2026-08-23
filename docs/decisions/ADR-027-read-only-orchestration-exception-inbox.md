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

For unresolved checkpoints, current branch, HEAD, and working-path fingerprint
remain freshness evidence. For a terminal `PUBLISHED` checkpoint, immutable
publication evidence is validated first and current repository state is not
used to invalidate the historical outcome. Terminal exclusion requires one
complete chain linking the authoritative task and filename, exact review
bundle, authorized owner/controller `APPROVE` decision, feature line, review
and finalized commit identities, and one canonical successful `PUSHED`
finalization record. A recorded `.agent_runner/finalize/` directory resolves
only to its `finalize.jsonl` child; other directory inference is prohibited.

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
- Later authorized feature-line commits or working-path changes do not create
  false exceptions for a fully validated historical publication.
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

## Reasoning labels

- **FACT:** `.agent_runner/finalize/finalize.jsonl` is the canonical append-only
  finalization boundary and `PUSHED` is its successful publication outcome.
- **ASSUMPTION:** Existing local task, bundle, decision, Git-object, and JSONL
  evidence remains available when the historical inbox projection is queried.
- **INFERENCE:** Mutable current HEAD and working paths can prove unresolved
  evidence stale, but cannot invalidate a separately complete immutable
  terminal publication chain.
- **PROPOSAL:** None; this accepted decision records the implemented boundary.
