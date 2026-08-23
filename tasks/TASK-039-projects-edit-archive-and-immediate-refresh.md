# TASK-039 — Projects edit, archive, and immediate refresh

STATUS: APPROVED

## Objective

Extend the usable Projects page so active projects can be edited or explicitly archived, archived projects remain visible as read-only records, and every successful edit or archive immediately refreshes the page while retaining clear success feedback.

## Business context

TASK-033 delivered project creation, listing, selection, and details. The preserved TASK-034 attempt proved the edit/archive service behavior and tests but was not published because its rework path could not safely resume and its page remained stale after successful mutations. This clean task re-establishes the bounded feature on the latest main-based branch after TASK-038 governance hardening.

## Facts

- The Project model already has unique name, optional description, and status fields; no migration is required.
- Existing creation trims inputs, converts blank descriptions to null, enforces exact-name uniqueness, and safely translates database uniqueness races.
- Existing page access flows through ProjectService and ProjectRepository inside session_scope.
- Canonical statuses for this slice are exactly `active` and `archived`; unknown values fail closed.
- Archived projects remain in the existing list and ordering.
- Successful edit/archive must trigger a native Streamlit rerun so stale details or controls are not left visible.
- A short success notice must survive that one rerun through bounded page session state.
- No new repository file is authorized other than this TASK-039 record.

## In scope

- Add active-project editing for name and optional description with creation-equivalent normalization, validation, exact-name uniqueness, and safe IntegrityError translation.
- Add a one-way active-to-archived service operation using the existing status field.
- Add deterministic missing, archived, and unknown-status outcomes without mutation.
- Add repository save behavior only as required to flush and refresh edited rows.
- Add native Streamlit edit and separately confirmed archive forms for active projects.
- Label archived projects in the selector and details, and render archived/unknown-status records read-only with no mutation controls.
- After successful edit or archive, store one bounded success notice, invoke native `st.rerun()`, consume that notice on the next render, and show fresh persisted details/state.
- Avoid rerun on validation, duplicate, missing, conflict, confirmation, or unexpected failure.
- Add deterministic service, repository, and isolated page coverage, including exactly one rerun on success and no rerun on failure.
- Update README project capabilities and deferred features.

## Explicitly out of scope

- Deletion, restoration/unarchive, lifecycle history, audit events, permissions, authentication, roles, search, filtering, pagination, bulk actions, or new project fields.
- Database schema, migration, constraint, index, relationship, or seed changes.
- Case-insensitive/fuzzy uniqueness, custom components, HTML, CSS, JavaScript, themes, or frontend dependencies.
- Main, deployment, production data, credentials, secrets, remote mutation, push, merge, tag, reset, rebase, or history rewrite.
- Broad page, service, repository, navigation, session, or application architecture rewrites.
- Any new source, test, documentation, fixture, helper, migration, or task file other than TASK-039.

## Allowed changed-file scope

- `tasks/TASK-039-projects-edit-archive-and-immediate-refresh.md`
- `advancore/pages/projects.py`
- `advancore/services/project_service.py`
- `advancore/repositories/project.py`
- `tests/test_project_service.py`
- `tests/test_repositories.py`
- `tests/test_projects_page.py`
- `README.md`

## Database impact

None. Runtime operations may update ordinary Project rows through the existing transaction boundary only.

## Safety requirements

- `agent_runner` task lifecycle and review gates remain authoritative.
- Kimi-Swarm remains primary where available; Codex desktop is the approved bounded local fallback.
- Workers cannot approve or publish their own work.
- Unknown lifecycle or UI state fails closed and does not mutate a project.
- Errors shown to users must not expose exception text, SQL, credentials, tokens, tracebacks, or environment details.
- No staging, commit, push, merge, deployment, reset, or remote mutation occurs during implementation/verification.

## Acceptance criteria

- Active project details show pre-populated native edit controls and a separate archive confirmation form.
- Edit normalization and validation match creation rules; keeping the same exact name is allowed and another project's exact name is rejected.
- IntegrityError during edit becomes the deterministic duplicate-name message.
- Successful edit changes exactly the selected project without creating another record.
- Archive requires both explicit confirmation and submission and changes exactly one active project to archived.
- Archived projects remain listed, are clearly labelled, show fresh archived status, and expose no edit/archive controls.
- Unknown statuses are read-only and cannot be edited or archived.
- Missing, archived, duplicate, invalid, unconfirmed, and unexpected outcomes never claim success or trigger rerun.
- Each successful edit or archive stores one bounded notice and calls `st.rerun()` exactly once; the next render consumes the notice and displays fresh state.
- Existing create/list/select/detail behavior remains working.
- No schema, deletion, restoration, permissions, history, search, bulk, production, or deployment behavior is added.
- All changed paths are within the exact approved scope and no new file exists other than TASK-039.

## Test requirements

- Cover normalized edit persistence, blank/overlong rejection without mutation, 200-character acceptance, blank-description normalization, unchanged self-name, duplicate other-name, and edit-time IntegrityError translation.
- Cover missing/archived/unknown edit outcomes and active archive plus missing/already-archived/unknown archive outcomes.
- Cover repository flush/refresh and persistence with isolated SQLite.
- Cover active forms, pre-population, archive confirmation, archived list/detail/read-only behavior, and generic safe errors.
- Cover exactly one rerun and retained success notice after successful edit/archive, then verify the next render shows updated values/status.
- Assert no rerun and no false success for every failed or unconfirmed path.
- Run focused project tests, then the complete `tests/` suite with the local test database setting.
- Run compilation/import checks, `git diff --check`, staged-file check, and exact scope/new-file verification.

## Constraints

- Preserve page → service → repository → session dependency direction.
- Service code must not import Streamlit; page code must not issue SQL or manage transactions.
- Use native Streamlit controls and bounded session state only.
- Preserve existing behavior outside this vertical slice and prefer small reversible changes.
- Stop if a schema, authorization, compliance, deletion, restoration, or out-of-scope decision is required.
- Completion requires the AGENTS.md report.

## Owner decisions

None.

## Completion report

### Implemented

- Added shared project field normalization plus active-project edit and one-way archive service operations with deterministic safe lifecycle errors.
- Added repository save/refresh behavior for ordinary Project updates.
- Added native edit and confirmed archive forms, archived list labels, and read-only archived/unknown-status details.
- Added exactly-one immediate Streamlit rerun after successful edit/archive and a bounded one-time success notice consumed on the fresh render.
- Added focused service, repository, and page coverage and updated the README.

### Files changed

- `tasks/TASK-039-projects-edit-archive-and-immediate-refresh.md`
- `advancore/pages/projects.py`
- `advancore/services/project_service.py`
- `advancore/repositories/project.py`
- `tests/test_project_service.py`
- `tests/test_repositories.py`
- `tests/test_projects_page.py`
- `README.md`

### Database changes

None. Existing Project columns and transaction boundaries are reused.

### Tests executed and results

- Focused Projects tests: 57 passed.
- Full repository suite: 718 passed.
- Python compile and modified-module import checks passed.
- Streamlit in-process app smoke check passed on the Projects route with zero exceptions, all three forms present, and no UI errors or warnings.
- `git diff --check`, empty-index, exact-scope, and new-file checks passed.

### Assumptions

- Project lifecycle values remain exactly `active` and `archived`; unknown values remain read-only.
- Exact-match, case-sensitive project-name uniqueness remains unchanged.

### Risks / unresolved issues

- Restoration, permissions, lifecycle history, deletion, search, and bulk actions remain intentionally deferred.
- Publication and deployment remain separate controller/owner-gated actions.

### Decisions required

None.

### Recommended next step

Perform independent controller review and a local app startup smoke check, then preserve and publish the feature branch only if both pass.
