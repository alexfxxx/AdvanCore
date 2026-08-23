# TASK-041 — Usable dashboard overview counts

STATUS: READY

## Objective

Replace the Dashboard's connection-only status with a read-only operational overview showing bounded project and knowledge counts while preserving safe database failure handling.

## Business context

Projects and Knowledge Hub now contain usable data, but the landing Dashboard provides no summary. A small read-only overview makes the application immediately more informative without defining commercial KPIs, trends, targets, permissions, or compliance rules.

## Facts

- Project statuses used by current features are `active` and `archived`; unknown statuses fail closed elsewhere.
- Knowledge created by the first hub slice has status `draft`; other statuses may already exist and must not be misclassified.
- Existing repositories list projects and knowledge items in deterministic order.
- Dashboard currently renders shell/database status only.
- No schema or migration is needed.

## In scope

- Add an injected DashboardService that derives total, active, archived, and other project counts plus total, draft, and other knowledge counts from repository results.
- Use an immutable bounded summary value object.
- Render native Streamlit metrics and concise navigation guidance on Dashboard.
- Keep the existing core-shell operational notice.
- Render one generic database-unavailable message without raw exception details when summary loading fails.
- Add focused deterministic service/page tests and update README.

## Explicitly out of scope

- Revenue, cost, utilization, fleet, customer, contract, employee, compliance, performance, trend, target, forecast, chart, date-range, or business KPI definitions.
- Row-level data, recent-item content, activity logging, search, filtering, mutation, links, drill-down, refresh controls, caching, or background jobs.
- Authentication, authorization, permissions, roles, tenant/customer rules, production telemetry, or external integrations.
- Database schema/migration/index/seed changes, custom components/HTML/CSS/JS, dependencies, main, deployment, credentials, production data, remote mutation, push, merge, reset, or history rewrite.
- Any new repository file except the task, dashboard service, and two focused test files listed below.

## Allowed changed-file scope

- `tasks/TASK-041-usable-dashboard-overview-counts.md`
- `advancore/pages/dashboard.py`
- `advancore/services/dashboard_service.py`
- `tests/test_dashboard_service.py`
- `tests/test_dashboard_page.py`
- `README.md`

## Database impact

None. Read existing rows only through repositories inside the established session boundary.

## Safety requirements

- Dashboard is read-only and cannot mutate application data.
- Unknown statuses are counted as `other`, not silently treated as active/archived/draft.
- Failures show no SQL, credentials, URLs, tokens, tracebacks, environment details, or raw exceptions.
- Governance lifecycle/review gates remain authoritative; no implementation publication actions occur before approval.

## Acceptance criteria

- Dashboard shows total, active, archived, and other project counts.
- Dashboard shows total, draft, and other knowledge counts.
- Counts are deterministic, internally consistent, and derived only from repository results.
- Empty repositories show zeros without warning/error.
- Unknown statuses increase only the corresponding `other` count.
- Database/repository failure shows one concise safe unavailable message and no misleading metrics.
- Existing navigation and other pages remain unchanged.
- No business KPI, row detail, mutation, schema, permission, integration, deployment, or sensitive-data behavior is added.
- Exact changed paths remain within scope.

## Test requirements

- Test empty, populated, mixed-status, and unknown-status service summaries.
- Test page metrics, zero state, generic failure/no leakage, and absence of metrics on failure.
- Run focused dashboard tests and full `tests/` suite with local test database setting.
- Run compile/import checks, in-process Dashboard smoke check, `git diff --check`, empty-index, exact-scope, and new-file verification.

## Constraints

- Preserve page → service → repository → session dependency direction.
- Service must not import Streamlit; page must not issue SQL or manage transactions.
- Do not infer KPIs, targets, legal/commercial rules, or access policy.
- Prefer small reversible changes and stop for schema/out-of-scope needs.
- Completion requires the AGENTS.md report.

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
