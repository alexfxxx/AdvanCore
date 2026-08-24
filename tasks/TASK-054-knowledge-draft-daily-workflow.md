# TASK-054 — Knowledge Draft Daily Workflow

STATUS: REVIEW

## Objective

Make the existing Knowledge Hub useful for a basic daily loop by allowing saved
drafts to be edited or archived with an immediate refreshed screen.

## In scope

- Edit the title and content of draft knowledge items.
- Archive a draft after explicit confirmation.
- Show archived items as clearly labelled, read-only records.
- Refresh immediately after edit/archive and show a controlled success notice.
- Preserve generic error handling without displaying internal details.

## Out of scope

Knowledge approval, publication, deletion, project linking, search, AI
generation, customer data, permissions, authentication, or business policy.

## Allowed changed-file scope

- `advancore/repositories/knowledge.py`
- `advancore/services/knowledge_service.py`
- `advancore/pages/knowledge_hub.py`
- `tests/test_knowledge_service.py`
- `tests/test_knowledge_hub_page.py`
- `tasks/TASK-054-knowledge-draft-daily-workflow.md`
- `README.md`

## Owner decisions

None. Approval/publication rules remain deferred rather than inferred.

## Completion report

### Implemented

- Added validated draft editing and one-way archiving.
- Added confirmation, read-only archived presentation, safe feedback and
  immediate refreshed results in the Knowledge Hub.

### Database changes

None.

### Tests executed and results

- Knowledge service and page suites: 30 passed.
- Repository suite: 9 passed against the local test database.
- Full repository suite after integration: 858 passed.
- `git diff --check`: passed.

### Decisions required

- Independent review and implementation approval remain manual.
