# AdvanCore Current State

Status date: 2026-08-29

## Summary

FACT: AdvanCore is a usable local v0.1 platform foundation with bounded Projects
and Knowledge workflows, lifecycle activity visibility, operational transport
registers, a decoupled local console, local recovery support, and an
exception-based agent-control system.

FACT: It is not yet a production transport ERP. Early customer, route, driver,
fleet, fuel and financial registers exist, but payroll, invoicing, profitability
and complete owner-approved business workflows remain future module work.

## Technology and persistence

- Python 3.10, Streamlit, SQLAlchemy, psycopg, and PostgreSQL 16.
- PostgreSQL stores operational application data through `DATABASE_URL`.
- Alembic owns schema migration history and includes a baseline migration.
- Docker Compose and `scripts/start-advancore.sh` support the consolidated local
  environment without deleting the saved legacy database volume.
- GitHub stores approved code, task specifications, architecture decisions,
  tests, and runbooks.

## Usable local application

FACT: The FastAPI-served interface at `http://127.0.0.1:8000` is the primary
AdvanCore app and owner starting point. It provides the customizable command
workspace, governed Owner Goal controls, readiness, bounded Projects and
Knowledge summaries, Fleet overview and details, Dispatch exceptions, and Fuel
benchmark intelligence.

The Streamlit interface at `http://127.0.0.1:8501` is temporary admin/editing
support while the following existing forms transfer into the primary app:

- Executive Command Center: light responsive layout, real platform counts,
  Kimi usage-policy visibility, AI worker-role visibility, and persistent
  show/hide preferences for approved modules and worker cards.
- Projects: create, list, select, edit, and explicitly archive projects, with
  archived records retained as read-only.
- Knowledge Hub: create, list, select, edit, and explicitly archive knowledge
  drafts, with archived records retained as read-only.
- Activity Log: read-only lifecycle records with entity and action filters.
- AI Center: read-only owner exception inbox for governed automation.
- Settings: read-only local application and database readiness.

Project and Knowledge mutations immediately refresh their visible saved state
and record bounded lifecycle activity. The interface uses no placeholder
financial, route, vehicle, driver, or customer figures.

## Governed AI development control

The repository contains the governed path from owner goal to bounded task,
worker execution, verification, repair, controller review, and safe feature-
branch publication. The permanent boundaries are:

- `agent_runner` remains the execution authority boundary.
- Controller policy reserves Kimi Swarm for eligibility-gated large or genuinely
  parallel work and prefers Gemini for normal bounded implementation.
- FACT: executable unattended routing still evaluates `kimi-swarm`, then
  `gemini`, then `codex`; changing that sequence requires separate governed work.
- Codex remains the controller and final approved fallback.
- Worker inputs use explicit data-access boundaries rather than inheriting the
  controller's complete environment.
- GitHub remains source of truth, and critical or ambiguous work fails closed.
- Owner involvement is intended to be exception-based, not stage-by-stage.

## Verification state

FACT: Repository checks cover models, services, migrations, API contracts,
frontend contracts, recovery and agent governance. Exact current release
evidence is recorded per reviewed feature branch rather than inferred here.

Coverage includes models, repositories, services, pages, migrations, local
startup, agent-runner governance, orchestration, worker routing and fallback,
usage guardrails, activity recording, dashboard preferences, and the local UI
theme. Pull requests also run GitHub verification and secret scanning.

## Current maturity and boundaries

FACT: The integration branch is `projects-lifecycle-recovery`; it is not
production and has not been merged into `main`.

FACT: The current application is designed for one local owner. There is no
real multi-user login, role/permission model, public network exposure, Android
deployment, or production operations environment.

FACT: Knowledge review/approval, project linking in the user interface,
search, attachments, source metadata, restore/delete flows, and advanced
business reporting remain deferred.

INFERENCE: The platform foundation is strong enough for the next bounded
business slice, but the owner must choose which real workflow delivers the
most value before its rules or data model are implemented.

## Immediate risks and limitations

1. Public or phone access would be unsafe without a separately designed
   authentication, authorization, network, and deployment boundary.
2. Provider quota data is not universally available and must never be invented;
   actual bounded provider attempts supply availability evidence.
3. The existing local example database password must never be reused for a
   production environment.
4. Commercial, transport, employment, tax, and compliance rules are not yet
   approved in enough detail for autonomous implementation.
5. The growing integration branch still needs an explicit release review before
   any future merge to `main` or deployment.

## Recommended next choices

No architecture rewrite is required. The next owner discussion should choose
one of these bounded directions:

1. Define real authentication and safe mobile access before exposing the app
   beyond this Mac.
2. Define the Knowledge review/approval workflow so draft information can
   become governed official knowledge.
3. Select one real business vertical slice—such as customer/contracts, routes,
   fleet, or purchase-order monitoring—and supply the minimum confirmed rules
   and sample fields needed for its task specification.

Until one of those choices is approved, workers can continue safe maintenance,
documentation, test, and usability repairs without inventing business policy.
