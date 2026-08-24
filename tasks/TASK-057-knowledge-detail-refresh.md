# TASK-057 — Knowledge Detail Refresh

STATUS: REVIEW

## Objective

Ensure the read-only Knowledge details content immediately shows the saved
value after a successful edit instead of retaining Streamlit's stale widget
state.

## In scope

- Give the read-only content widget a deterministic saved-content identity.
- Remove superseded detail-widget state for the selected item before render.
- Preserve the existing edit, archive, validation, and fail-closed behavior.
- Add regression coverage that models Streamlit's key-based widget state.

## Out of scope

Database changes, lifecycle changes, search, approval, project linking,
attachments, deletion, worker routing, credentials, deployment, or `main`.

## Allowed changed-file scope

- `tasks/TASK-057-knowledge-detail-refresh.md`
- `advancore/pages/knowledge_hub.py`
- `tests/test_knowledge_hub_page.py`

## Owner decisions

None. The owner approved continuing bounded usability tasks on 24 August 2026.

## Completion report

### Implemented

- Derived the disabled details widget identity from the item identifier and a
  short SHA-256 digest of its current saved content.
- Removed superseded detail-widget keys before rendering so Streamlit cannot
  reuse an earlier saved value.
- Improved the isolated Streamlit fake to model real key-based disabled-widget
  state and added a regression that fails under the previous fixed key.

### Files changed

- `tasks/TASK-057-knowledge-detail-refresh.md`
- `advancore/pages/knowledge_hub.py`
- `tests/test_knowledge_hub_page.py`

### Database changes

None.

### Tests executed and results

- Focused Knowledge Hub page tests: 14 passed.
- Full repository suite: 875 passed.
- `git diff --check`: passed.
- Live browser edit: the read-only details content immediately changed to the
  newly saved value after the edit rerun.
- Live cleanup: the temporary test draft was archived.

### Assumptions

- A short SHA-256 digest is used only as a non-secret widget identity; raw
  knowledge content is never placed in the key.

### Risks / unresolved issues

- The live archive check exposed a separate stale selectbox display label; the
  details status and saved database value were correct. This is deferred to
  TASK-058 rather than expanding scope.

### Decisions required

- Review and feature-branch publication remain governed follow-up actions.

### Recommended next step

- Review and publish the scoped repair, then address the separately observed
  post-archive selector-label refresh defect.
