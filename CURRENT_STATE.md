# AdvanCore Current State

Status date: 2026-08-20

## Repository overview
AdvanCore is currently a small platform-foundation repository rather than a full ERP implementation.

## Current technology stack
- Python 3.10.9
- Streamlit 1.61.1
- SQLAlchemy 2.0.52
- python-dotenv 1.2.2
- psycopg 3.3.4
- PostgreSQL 16 target database through DATABASE_URL
- Docker local environment
- GitHub version control

## Existing application structure
The root `app.py` provides Streamlit navigation for:
- Dashboard
- Knowledge Hub
- Projects
- AI Center
- Activity Log
- Settings

## Existing data models
Current SQLAlchemy models include:
- Project
- KnowledgeItem
- ActivityLog
- SystemSetting
- shared Base model

## Existing service layer
`advancore/services/database.py`:
- loads environment variables
- requires DATABASE_URL
- creates a SQLAlchemy engine
- provides a database connectivity check
- provides `initialize_database()` using `Base.metadata.create_all()`

## Existing repository support
- Docker compose configuration exists.
- requirements.txt exists.
- tests/ exists but contains only an empty `tests/_init_.py` with a non-standard filename; pytest is not installed in `.venv`.
- docs/ exists but contains only README placeholders in each subdirectory.
- `.agents/skills/developing-with-streamlit` is a symlink into `.venv` and points to the Streamlit package's bundled skill.

## Current maturity assessment
FACT: This is an early foundation (v0.1 / Gate 0 direction), not yet a transport ERP.
FACT: The project already has the right broad separation of UI, models and services for incremental expansion.
FACT: The database layer currently uses direct metadata creation rather than an explicit migration workflow.
INFERENCE: Introducing controlled migrations should happen before significant production schema growth.
INFERENCE: Test coverage should be strengthened before agents are allowed to make larger autonomous changes.

## Immediate risks
1. Autonomous agents could over-expand scope if given open-ended requests.
2. Schema growth without migrations could become difficult to control.
3. **No real tests exist** (`tests/_init_.py` is empty and misnamed), reducing confidence in automated refactoring.
4. Business and compliance rules are not yet represented in a structured approved knowledge system.
5. `docker-compose.yml` contains a hard-coded local password; production deployments must use injected secrets, not this file.
6. No migration framework is in place; schema changes currently rely on `Base.metadata.create_all()`.

## Recommended next sequence
1. Review and approve the repository audit (TASK-001).
2. Fix the test package name (`tests/__init__.py`) and install pytest in `.venv`.
3. Establish migration strategy and baseline tests.
4. Define core entities and shared conventions.
5. Implement business modules one bounded task at a time.

## Owner decisions not yet required
No major architecture rewrite is required at this stage. The existing foundation should be preserved until TASK-001 is completed and reviewed.
