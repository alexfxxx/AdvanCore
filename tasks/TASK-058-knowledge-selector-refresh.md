# TASK-058 — Knowledge Selector Refresh

STATUS: REVIEW

## Objective

Ensure the Knowledge selector immediately displays the saved title/status label
after an edit or archive while keeping the same item selected.

## In scope

- Version the Streamlit selector widget from the current saved list labels.
- Preserve the selected item separately across a label-changing rerun.
- Remove superseded selector-widget state before rendering.
- Add regression coverage for the observed draft-to-archived stale label.

## Out of scope

Lifecycle changes, sorting changes, search, database changes, deletion,
permissions, worker policy, credentials, deployment, or `main`.

## Allowed changed-file scope

- `tasks/TASK-058-knowledge-selector-refresh.md`
- `advancore/pages/knowledge_hub.py`
- `tests/test_knowledge_hub_page.py`

## Owner decisions

None. This is a bounded repair of live behavior observed during TASK-057.

## Completion report

### Implemented

- Versioned the Knowledge selectbox key from a digest of current item IDs,
  titles, and statuses without exposing those values in the key.
- Preserved the selected item in separate bounded session state so a changed
  label does not reset the user to another record.
- Removed legacy and superseded selectbox state before rendering.
- Extended the Streamlit fake and added regression coverage for the exact
  draft-to-archived transition.

### Files changed

- `tasks/TASK-058-knowledge-selector-refresh.md`
- `advancore/pages/knowledge_hub.py`
- `tests/test_knowledge_hub_page.py`

### Database changes

None.

### Tests executed and results

- Focused Knowledge Hub page tests: 15 passed.
- Full repository suite: 876 passed.
- `git diff --check`: passed.
- Live browser archive: the same selected record immediately changed from its
  draft label to its archived label and rendered read-only details.

### Assumptions

- Existing creation-order list behavior remains unchanged.

### Risks / unresolved issues

- No known issue within scope. Creation-order list behavior is unchanged.

### Decisions required

- Review and feature-branch publication remain governed follow-up actions.

### Recommended next step

- Review and publish the scoped repair, then continue the bounded usability
  backlog.
