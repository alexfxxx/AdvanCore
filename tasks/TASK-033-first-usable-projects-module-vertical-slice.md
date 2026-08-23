# TASK-033 — First usable Projects module vertical slice

STATUS: READY

## Objective

Replace the placeholder Projects page with a safe Streamlit workflow that lists, creates, and views projects through the existing service, repository, and database session boundaries.

## Business context

Projects is an initial AdvanCore platform component, but its current page is only a placeholder. This bounded vertical slice will make the module usable for basic project registration and viewing while preserving the established layered architecture and deferring higher-risk lifecycle and access-control capabilities.

## Facts

- The current Projects page only renders a heading and placeholder text.
- The existing Project model has an integer identifier, required unique name limited to 200 characters, optional description, status defaulting to active, and timestamps.
- ProjectRepository already supports adding projects, listing projects, retrieving by identifier, and exact-name lookup.
- ProjectService already exposes create, list, identifier lookup, and exact-name lookup operations.
- The established dependency direction is Streamlit page to application service to repository to SQLAlchemy session to PostgreSQL.
- The existing session_scope boundary commits successful work, rolls back exceptions, and always closes the session.
- Existing service tests use a fake repository, and repository tests use isolated SQLite infrastructure.
- No page render tests currently exist.
- PostgreSQL is the operational database, while GitHub remains the source of truth for approved code and documentation.

## Assumptions

- Project names will retain the database's existing exact-match uniqueness semantics; case-insensitive uniqueness is not introduced.
- Leading and trailing whitespace may be removed from submitted names and descriptions as input normalization.
- An empty normalized description may be stored as null.
- Project list ordering will continue to use the repository's existing creation-time ordering.
- The existing render-function page structure and sidebar navigation will be preserved for this bounded slice.
- Native Streamlit controls and forms are sufficient; no custom component, CSS, or new frontend dependency is required.
- Concise user guidance can be added to the repository README without creating a broader documentation architecture.

## In scope

- Replace the placeholder Projects page with native Streamlit list, create, and read-only detail behavior.
- Construct ProjectRepository and ProjectService within the existing session_scope boundary; keep SQLAlchemy access out of the page.
- Display each project's existing name, optional description, and status without introducing additional business fields.
- Provide a creation form accepting only name and optional description.
- Normalize and validate submitted input, including rejecting blank names and names longer than the model's 200-character limit.
- Default every newly created project to active and do not expose status selection during creation.
- Handle duplicate project names deterministically at the service boundary, including translation of database uniqueness conflicts into a presentation-safe domain outcome.
- Show clear empty, loading, successful creation, validation, duplicate-name, missing-record, and unexpected-error states.
- Ensure unexpected errors fail closed, do not claim success, and do not expose credentials, SQL details, stack traces, or sensitive runtime information in the UI.
- Add deterministic service tests for validation, normalization, active defaults, duplicate handling, and existing list/view behavior.
- Add deterministic Projects page tests using isolated fakes or mocks so no live PostgreSQL connection, production data, or credentials are required.
- Add concise README documentation describing the available Projects behavior and explicitly deferred capabilities.
- Run focused tests and the full existing test suite, then produce the standard completion report required by AGENTS.md.

## Explicitly out of scope

- Editing project names or descriptions after creation.
- Archiving projects or changing project status.
- Deleting projects.
- Permissions, authentication, authorization, or role-based access control.
- Activity or audit-log creation for project actions.
- New Project fields, tables, relationships, constraints, indexes, or schema migrations.
- Changes to existing commercial, operational, or compliance rules.
- Case-insensitive, fuzzy, or customer-specific duplicate-name rules.
- Bulk import, export, search, filtering, sorting controls, pagination, or analytics.
- Changes to application-wide navigation or a broad Streamlit architecture rewrite.
- New custom components, custom CSS, themes, or frontend dependencies.
- Production data access, deployment, release operations, or changes outside the owner-designated feature work.
- Any lifecycle transition or implementation activity without separate explicit task-content and implementation authorization.

## Allowed changed-file scope

- `tasks/TASK-033-first-usable-projects-module-vertical-slice.md`
- `advancore/pages/projects.py`
- `advancore/services/project_service.py`
- `tests/test_project_service.py`
- `tests/test_projects_page.py`
- `README.md`

## Database impact

None. The implementation may create ordinary Project rows only through the existing model and transaction boundary during authorised use. No schema, migration, seed-data, or production-data changes are permitted; automated tests must use fakes, mocks, or disposable isolated databases.

## Safety requirements

- GitHub remains the source-of-truth.
- `main` remains untouched and non-executable unless explicitly approved.
- Worker/swarm cannot approve its own work.
- No automatic staging, commit, push, merge, tag, deploy, switch, reset,
  rebase, or history rewrite.
- This generated task is DRAFT and cannot execute until a valid
  `DRAFT -> READY` controller/owner transition.
- Unknown, unsafe, malformed, conflicting, or ambiguous states fail closed.
- The planner proposed only; the runner constructed this DRAFT; the
  controller/owner must authorize execution.

## Acceptance criteria

- Selecting Projects renders usable list, create, and read-only detail behavior instead of placeholder copy.
- The page accesses project persistence only through ProjectService, ProjectRepository, and session_scope.
- When no projects exist, the page displays an explicit empty state and still permits creation.
- While project data is being obtained, the page renders a stable loading indication using native Streamlit behavior.
- The list presents projects deterministically and permits one project to be selected for viewing.
- The detail view displays only the selected project's name, optional description, and status, with a clear missing-description state.
- The creation form accepts only name and optional description and batches submission through a native Streamlit form.
- A submitted name is normalized, must not be blank, and must not exceed 200 characters.
- A normalized blank description is treated as absent.
- Every newly created project has status active, and the user cannot choose another status.
- A successful submission persists exactly one project, displays confirmation, and makes the created project available to the list/view workflow.
- Duplicate exact names are rejected with a clear user-safe message, including when the database uniqueness constraint detects a race after any pre-check.
- Validation, duplicate, missing-record, and unexpected persistence errors never display a false success state.
- Unexpected errors are shown as concise generic failures without leaking exception details, SQL, credentials, or environment values.
- No edit, archive, status-change, deletion, permissions, activity logging, or migration behavior is introduced.
- Service and page tests are deterministic and do not require a live Streamlit server, PostgreSQL instance, production credentials, or production data.
- README documentation concisely describes the available Projects workflow and deferred functionality.
- All focused tests and the full existing test suite pass.
- The completion report covers implemented work, files changed, database changes, tests and results, assumptions, risks, decisions required, and recommended next step.

## Test requirements

- Extend tests/test_project_service.py to verify trimming and validation of names, rejection of blank names, rejection of names over 200 characters, optional-description normalization, and active status on creation.
- Add service tests proving an exact duplicate is rejected and a repository or database uniqueness conflict is translated into the same deterministic duplicate-name outcome.
- Retain or extend service tests for list and identifier-based retrieval delegation.
- Add tests/test_projects_page.py with isolated service, repository, session, and Streamlit test doubles or supported Streamlit testing APIs.
- Test the populated list and selected-project detail state.
- Test the empty-project state.
- Test valid creation, success feedback, and active default behavior.
- Test invalid blank and overlength names without persistence calls.
- Test duplicate-name feedback without false success.
- Test missing-record and generic loading or persistence failure states, confirming exception internals are not rendered.
- Run .venv/bin/python -m pytest tests/test_project_service.py tests/test_projects_page.py -v.
- Run .venv/bin/python -m pytest tests/ -v.
- Run a Python compile or import sanity check for the modified modules without accessing a live database.

## Constraints

- This proposal provides planning assistance only and confers no implementation or publication authority.
- Require separate explicit owner or controller authorization of the task content before any lifecycle advancement.
- Require separate explicit implementation authorization before code changes begin.
- Read AGENTS.md and the resulting task file before implementation, then inspect existing implementation and dependencies and produce an implementation plan.
- Preserve fail-closed governance and stop when required authorization, repository state, or scope validation is absent or ambiguous.
- Keep changes limited to the allowed repository-relative file scope.
- Preserve existing working behavior outside the Projects module.
- Keep presentation logic in the page, use-case validation and error translation in the service, persistence operations in the repository, and transaction handling in session_scope.
- The service must not import Streamlit, and the page must not issue SQLAlchemy queries or create a separate engine.
- Use the existing Project model and repository API; do not add fields or migrations.
- Use native Streamlit elements and accessible labels; do not introduce deprecated use_container_width usage, custom HTML, or custom CSS.
- Do not access, print, log, or commit credentials, secrets, tokens, environment-file contents, or production data.
- Do not invent Singapore legal or compliance requirements; flag any newly discovered compliance issue for owner verification.
- Do not perform repository-history, remote, release, or deployment operations.
- Do not work on the default integration line or expand the task beyond the owner-designated Projects feature work.
- Use isolated tests and preserve deterministic outcomes independent of test execution order.
- Any unexpected need for schema, permissions, activity logging, or architecture changes must stop implementation and be returned for owner review.

## Owner decisions

None.

## Completion report

### Implemented

### Files changed

### Database changes

### Tests executed and results

### Assumptions

### Risks / unresolved issues

### Decisions required

### Recommended next step
