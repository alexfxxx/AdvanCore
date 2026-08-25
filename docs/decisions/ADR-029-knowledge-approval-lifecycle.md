# ADR-029 — Knowledge Approval Lifecycle

STATUS: ACCEPTED

## Context

AdvanCore can capture, edit, and archive Knowledge drafts, but it cannot yet
distinguish owner-approved official information from unreviewed material.
AI-generated or worker-generated information must not become official without
an explicit owner decision.

The application is currently single-owner and has no authenticated identity
model. A later interface task will add the explicit review and confirmation
control, and a later replacement task will preserve corrections as new drafts.

## Decision

Use a one-way `draft → approved` transition. The application service records
the fixed approver identity `owner` and an aware UTC timestamp; callers cannot
supply another identity. Approved title and content are read-only and cannot
return to draft. An approved item may be archived, but its approval evidence is
retained. Corrections require a new replacement draft rather than editing the
approved record.

Approval fields are nullable for existing and unapproved rows. Database checks
keep the two fields paired, require them for `approved`, forbid them for
`draft`, and reject blank approver identities. A successful approval records
one minimal `knowledge_approved` Activity Log event in the same caller-owned
transaction. The event contains no title, content, approver, credentials, or
free-text details.

TASK-074 deliberately exposes no approval button or agent-callable transport.
TASK-075 must add an explicit owner review and confirmation interface before
the transition is available through the application.

## Consequences

Official Knowledge becomes distinguishable, immutable, and auditable without
inventing a multi-user identity system. Existing rows migrate unchanged. The
literal `owner` identity is an acknowledged single-owner bridge and must be
replaced through a separately approved authentication/identity migration if
AdvanCore becomes multi-user.

## Database impact

- Add nullable `knowledge_items.approved_at`.
- Add nullable `knowledge_items.approved_by` with length 100.
- Add approval-pair, approved-required, draft-forbidden, and nonblank-approver
  check constraints.

## Owner approval

The owner approved these lifecycle rules and TASK-074 on 25 August 2026.
