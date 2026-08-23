# TASK-040 — First usable Knowledge Hub draft slice

STATUS: APPROVED

## Objective

Replace the Knowledge Hub placeholder with a bounded Streamlit workflow that creates draft knowledge items, lists them in deterministic order, and shows a selected item's read-only details.

## Business context

The application shell and Projects lifecycle are usable, but Knowledge Hub is still placeholder text. The existing KnowledgeItem model, migration, and repository already support the minimum storage needed for a useful draft capture/view slice without defining approval, search, AI, or access-control policy.

## Facts

- KnowledgeItem already has id, optional project_id, required title up to 300 characters, required text content, status default `draft`, optional source_type/reference, and timestamps.
- KnowledgeItemRepository already provides add, identifier lookup, chronological list, and project-filtered list.
- No service or usable Knowledge Hub page exists.
- PostgreSQL remains operational storage; tests use isolated fakes or SQLite.
- This slice creates only `draft` records with project/source fields absent.

## In scope

- Add a KnowledgeService using injected KnowledgeItemRepository.
- Validate and trim required title/content; reject blank values and titles over 300 characters.
- Create items with status exactly `draft` and project/source fields absent.
- List all items in repository order and retrieve by identifier.
- Replace the placeholder page with native Streamlit draft form, empty state, deterministic selector, and selected read-only detail showing title, status, content, and creation time when available.
- Render concise safe validation, creation, loading, and missing-record outcomes without exception internals.
- Add focused service/page tests and retain repository regression coverage.
- Update README with the bounded Knowledge Hub capability and deferred features.

## Explicitly out of scope

- Edit, delete, archive, approve, reject, review, publish, status transitions, version history, audit events, or workflow rules.
- Search, filtering, sorting controls, pagination, tags, categories, attachments, file upload, URL fetching, AI generation/summarization/embedding, or vector storage.
- Project linking, source_type/source_reference input, permissions, authentication, roles, ownership, or tenant/customer rules.
- Database schema, migration, constraint, index, relationship, or seed changes.
- Custom HTML/CSS/JavaScript/components, new dependencies, main, deployment, production data, credentials, remote mutation, push, merge, reset, or history rewrite.
- Any new repository file except the task, service, and two focused test files expressly listed below.

## Allowed changed-file scope

- `tasks/TASK-040-first-usable-knowledge-hub-draft-slice.md`
- `advancore/pages/knowledge_hub.py`
- `advancore/services/knowledge_service.py`
- `advancore/repositories/knowledge.py`
- `tests/test_knowledge_service.py`
- `tests/test_knowledge_hub_page.py`
- `tests/test_repositories.py`
- `README.md`

## Database impact

None. Use the existing knowledge_items table and columns; runtime creation may insert ordinary draft rows through the existing session boundary.

## Safety requirements

- `agent_runner` lifecycle/review gates remain authoritative and workers cannot self-approve or publish.
- Unknown or malformed input/state fails closed.
- Page errors do not expose SQL, credentials, tokens, environment details, tracebacks, or raw exceptions.
- No staging, commit, push, merge, deploy, reset, or remote mutation during implementation/verification.

## Acceptance criteria

- Knowledge Hub shows a native form with required title and content fields.
- Title/content are trimmed; blank title/content and normalized title over 300 characters are rejected without persistence or false success.
- A 300-character normalized title is accepted.
- Successful creation persists one item with status `draft` and null project/source fields.
- Empty state is clear; populated list is deterministic and selectable.
- Selected detail is read-only and shows title, status, content, and a safe created-at value when available.
- Missing selected records and unexpected create/load failures render deterministic safe messages.
- Existing app navigation and other pages remain unchanged.
- No approval/edit/delete/search/project-link/source/AI/access-control/schema/deployment behavior is added.
- Exact changed paths remain within scope.

## Test requirements

- Test service normalization, successful draft defaults, blank/overlong rejection, 300-character acceptance, list delegation, and identifier lookup.
- Test page empty/populated/detail states, successful create, invalid inputs, missing record, and safe generic failures/no false success.
- Retain isolated repository create/get/list coverage.
- Run focused Knowledge Hub/repository tests and full `tests/` suite with the local test database setting.
- Run compile/import checks, in-process Streamlit route smoke check, `git diff --check`, empty-index, exact-scope, and new-file verification.

## Constraints

- Preserve page → service → repository → session dependency direction.
- Service must not import Streamlit; page must not issue SQL or manage transactions.
- Do not infer approval, permissions, source, project-link, AI, legal, commercial, or compliance rules.
- Prefer small reversible changes and stop for any schema or out-of-scope requirement.
- Completion requires the AGENTS.md report.

## Owner decisions

None.

## Completion report

### Implemented

- Added an injected KnowledgeService with trimmed required-field validation and draft-only creation defaults.
- Replaced the placeholder Knowledge Hub with native draft creation, deterministic list/selection, empty state, and read-only details.
- Added safe validation, missing-record, creation, and loading outcomes without exception leakage.
- Added focused service/page coverage and README capability documentation.

### Files changed

- `tasks/TASK-040-first-usable-knowledge-hub-draft-slice.md`
- `advancore/pages/knowledge_hub.py`
- `advancore/services/knowledge_service.py`
- `tests/test_knowledge_service.py`
- `tests/test_knowledge_hub_page.py`
- `README.md`

### Database changes

None. The existing knowledge_items table and transaction boundary are reused.

### Tests executed and results

- Focused Knowledge Hub/repository suite: 24 passed.
- Full repository suite: 734 passed.
- Python compile/import checks and `git diff --check` passed.
- In-process Streamlit Knowledge Hub smoke check passed with zero exceptions, list/detail rendering, and no UI errors or warnings.
- Empty-index, exact-scope, and new-file checks passed.

### Assumptions

- This first slice creates only unlinked `draft` records and preserves repository creation order.
- Duplicate titles are permitted because the existing schema does not declare title uniqueness.

### Risks / unresolved issues

- Editing, approval, search, project linking, source metadata, attachments, AI features, permissions, and deletion remain intentionally deferred.
- Publication and deployment remain separately gated.

### Decisions required

None.

### Recommended next step

Perform independent controller review, then preserve and publish the stacked feature branch only if the exact diff and evidence pass.
