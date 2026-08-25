# TASK-075 — Owner Knowledge Approval UI

STATUS: REVIEW

## Objective

Add an explicit owner-facing review and confirmation interface that invokes the
TASK-074 Knowledge approval boundary without making approval available to AI
workers or silently changing saved Knowledge.

## Business context

TASK-074 established the owner-only, one-way `draft → approved` service and
database foundation. The Knowledge Hub still has no visible approval control,
so the owner cannot yet mark reviewed Knowledge as official through the app.

## Facts

- `KnowledgeService.approve_draft(item_id)` accepts no approver identity and
  records the fixed single-owner identity `owner`.
- Approval is irreversible and approved title/content are read-only.
- The saved Knowledge detail is already displayed above its lifecycle forms.
- The app is currently single-owner and has no login or role model.
- TASK-076 will add correction through replacement drafts and lineage.

## Approved interaction rules

- Show approval controls only for a saved `draft` item.
- State clearly that approval uses the saved title and content; unsaved edit
  fields are never approved.
- Require an explicit confirmation checkbox and a separate approval submit.
- Do not approve when confirmation is absent.
- On success, refresh the page and show a bounded success notice.
- Show approved time and the trusted `Owner` label on approved items.
- Approved items remain read-only but may be archived with confirmation.
- Archived and unsupported states expose no approval action.
- AI workers receive no direct approval interface or alternative service path.

## In scope

- Add a bounded presentation helper for owner approval.
- Add the explicit confirmation form to draft details.
- Add approved-state evidence and read-only guidance.
- Allow the existing archive UI to archive an approved item while preserving
  its approval metadata through the TASK-074 service.
- Add deterministic page tests for success, missing confirmation, known and
  unexpected failures, approved presentation, state refresh, and hidden actions.

## Out of scope

- Authentication, multi-user identity, roles, permissions, delegation,
  rejection, unapproval, direct approved-content edits, replacement drafts,
  version lineage, notifications, AI approval, database changes, deployment,
  or `main`.

## Allowed changed-file scope

- `tasks/TASK-075-owner-knowledge-approval-ui.md`
- `advancore/pages/knowledge_hub.py`
- `tests/test_knowledge_hub_page.py`

## Database impact

None. TASK-075 uses the TASK-074 schema and service boundary unchanged.

## Acceptance criteria

- [x] A draft displays one explicit owner approval form.
- [x] Approval requires confirmation and uses only the selected saved item ID.
- [x] Missing confirmation performs no service call and gives clear guidance.
- [x] Success refreshes to an approved, read-only view with approval evidence.
- [x] Approved Knowledge can be archived without losing approval evidence.
- [x] Archived, approved, and unsupported items expose no approval action.
- [x] Known lifecycle errors are readable; unexpected errors are generic and
      do not leak internal details or show false success.
- [x] Existing create, edit, archive, selection, and refresh behavior remains
      working.
- [x] Focused and full tests pass.
- [x] Completion report produced.

## Test requirements

- Cover confirmation gating, approval success, refresh notice, selected label
  refresh, approval evidence, immutable presentation, approved archive, known
  lifecycle failure, unexpected failure redaction, and hidden actions.
- Run focused Knowledge Hub tests, full repository tests, and
  `git diff --check`.

## Constraints

- Preserve page → service → repository → session dependency direction.
- Call only the approved `KnowledgeService.approve_draft(item_id)` boundary.
- Never accept or infer caller-supplied approver identity.
- Never place Knowledge content, credentials, or free text in success notices,
  widget identities, or Activity Log details.
- Do not add an agent-callable transport or weaken the TASK-074 lifecycle.

## Owner decisions

The owner approved continuation with TASK-075 on 25 August 2026. Existing
Knowledge Approval rules from TASK-074 remain authoritative.

## Completion report

### Implemented

- Added a draft-only owner approval form with separate review confirmation.
- Approval passes only the selected saved item ID to the TASK-074 service; typed
  but unsaved edit values are not approved.
- Added approved and archived-approved read-only views with approval time and a
  bounded `Owner` label.
- Added confirmed archive support for approved Knowledge while preserving its
  approval evidence.
- Added safe handling for lifecycle races and redacted unexpected failures.

### Files changed

- `advancore/pages/knowledge_hub.py`
- `tests/test_knowledge_hub_page.py`
- `tasks/TASK-075-owner-knowledge-approval-ui.md`

### Database changes

None.

### Tests and results

- Focused Knowledge, approval, and audit tests: 74 passed.
- Full repository suite: 954 passed, 1 intentionally skipped.
- `git diff --check` passed.
- GitHub PR #16 CI and GitGuardian security checks passed.

### Assumptions

- The current local single-owner application is the owner-facing interface;
  authentication remains a separate future decision.

### Risks / unresolved issues

- The app still has no authenticated multi-user identity. The fixed `Owner`
  identity is appropriate only for the current local single-owner operating
  model and does not claim to be an authentication control.
- Approved content cannot yet be corrected; TASK-076 will provide replacement
  drafts without mutating official history.

### Decisions required

None for this approved scope.

### Recommended next step

Merge green PR #16 into `projects-lifecycle-recovery` (never `main`), then
proceed to TASK-076 replacement-draft history.
