# AdvanCore Repository Map

**Date:** 2026-08-20  
**Branch:** `agent-control-foundation`  
**Task:** TASK-001 — Repository Audit and Architecture Map  
**Scope:** Audit and documentation only. No feature development, schema changes, or refactoring.

---

## 1. Overview

AdvanCore is an early-stage Python/Streamlit platform foundation. The current codebase is intentionally small: a single-page Streamlit application with placeholder modules, four SQLAlchemy models, and one database service. It is not yet a transport ERP or a multi-module business system.

This map documents the verified structure, technology choices, maturity level, and risks so that future agent tasks can operate from a known baseline.

---

## 2. Repository Structure

```
AdvanCore/
├── app.py                          # Streamlit entry point and navigation
├── requirements.txt                # Python dependencies
├── docker-compose.yml              # Local PostgreSQL container
├── pyrightconfig.json              # Pylance/Pyright configuration
├── README.md                       # Project overview
├── CURRENT_STATE.md                # Living maturity assessment
├── AGENTS.md                       # Agent development constitution
├── MASTER_SPEC.md                  # Long-term vision and non-goals
├── .env                            # Local environment variables (gitignored, not read)
├── .venv/                          # Local Python virtual environment
│
├── advancore/                      # Application package
│   ├── __init__.py                 # Empty
│   ├── config.py                   # App name, version, title constants
│   ├── models/                     # SQLAlchemy ORM models
│   │   ├── __init__.py             # Public model exports
│   │   ├── base.py                 # DeclarativeBase + TimestampMixin
│   │   ├── project.py              # Project entity
│   │   ├── knowledge.py            # KnowledgeItem entity
│   │   ├── activity.py             # ActivityLog entity
│   │   └── setting.py              # SystemSetting entity
│   ├── pages/                      # Streamlit page renderers
│   │   ├── __init__.py             # Empty
│   │   ├── dashboard.py            # Status + DB connectivity check
│   │   ├── knowledge_hub.py        # Placeholder
│   │   ├── projects.py             # Placeholder
│   │   ├── ai_center.py            # Placeholder
│   │   ├── activity_log.py         # Placeholder
│   │   └── settings.py             # Placeholder
│   └── services/                   # Backend services
│       ├── __init__.py             # Empty
│       └── database.py             # Engine, connection test, init
│
├── tests/                          # Test directory
│   └── _init_.py                   # Empty, non-standard name
│
├── docs/                           # Documentation areas
│   ├── architecture/               # Architecture maps and decisions
│   ├── business-rules/             # Approved business rules
│   └── decisions/                  # Architecture/product decisions
│
├── tasks/                          # Controlled work queue
│   ├── README.md                   # Task queue rules and status values
│   ├── TASK_TEMPLATE.md            # Template for new tasks
│   └── TASK-001-repository-audit.md# This audit task
│
└── data/                           # Data directory (currently empty except .gitkeep)
```

---

## 3. Technology Stack

| Component | Verified Version | Source |
|-----------|------------------|--------|
| Python | 3.10.9 | `.venv/bin/python --version` |
| Streamlit | 1.61.1 | `.venv/bin/python -c import streamlit` |
| SQLAlchemy | 2.0.52 | `.venv/bin/python -c import sqlalchemy` |
| python-dotenv | 1.2.2 | `.venv/bin/python -m pip freeze` |
| psycopg | 3.3.4 | `.venv/bin/python -m pip freeze` |
| PostgreSQL (target) | 16 | `docker-compose.yml` |
| pytest | **not installed in .venv** | `.venv/bin/python -m pytest` fails |

**Important:** The system/default Python (Anaconda) does not have the project dependencies installed. All verification must use `.venv/bin/python`.

---

## 4. UI / Frontend Architecture

- **Framework:** Streamlit 1.61.1.
- **Entry point:** `app.py`.
- **Navigation:** Sidebar radio button selects one of six hard-coded pages.
- **Page pattern:** Each page is a module under `advancore/pages/` with a single `render()` function.
- **Current state:**
  - Only `dashboard.py` contains real logic (a database connectivity check).
  - `knowledge_hub.py`, `projects.py`, `ai_center.py`, `activity_log.py`, and `settings.py` are placeholders with a header and a single sentence.
- **Page config:** Wide layout, title from `APP_TITLE`, brain emoji icon.

### Page inventory

| Page | File | Maturity | Notes |
|------|------|----------|-------|
| Dashboard | `advancore/pages/dashboard.py` | Functional | Calls `test_database_connection()` |
| Knowledge Hub | `advancore/pages/knowledge_hub.py` | Placeholder | One sentence |
| Projects | `advancore/pages/projects.py` | Placeholder | One sentence |
| AI Center | `advancore/pages/ai_center.py` | Placeholder | One sentence |
| Activity Log | `advancore/pages/activity_log.py` | Placeholder | One sentence |
| Settings | `advancore/pages/settings.py` | Placeholder | One sentence |

---

## 5. Service / Backend Architecture

- **Only service module:** `advancore/services/database.py`.
- **Responsibilities:**
  1. Load environment variables via `python-dotenv`.
  2. Require `DATABASE_URL`.
  3. Create a single SQLAlchemy 2.0 engine with `pool_pre_ping=True`.
  4. Provide `test_database_connection()` — executes `SELECT 1`.
  5. Provide `initialize_database()` — calls `Base.metadata.create_all()`.
- **Design notes:**
  - Module-level `engine` is created at import time.
  - No connection/session management abstraction beyond the engine.
  - No migration framework is in use; schema is created from metadata on demand.

---

## 6. Database Models and Relationships

All models inherit from `Base` (`DeclarativeBase`) and `TimestampMixin`.

### Base model (`advancore/models/base.py`)

- `Base` = SQLAlchemy 2.0 `DeclarativeBase`.
- `TimestampMixin` adds:
  - `created_at`: `DateTime(timezone=True)`, default `datetime.utcnow`, non-nullable.
  - `updated_at`: `DateTime(timezone=True)`, default `datetime.utcnow`, `onupdate=datetime.utcnow`, non-nullable.

### Models

#### `Project` → table `projects`

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | `Integer` | Primary key |
| `name` | `String(200)` | Unique, non-nullable |
| `description` | `Text` | Nullable |
| `status` | `String(50)` | Default `"active"`, non-nullable |
| `created_at` | `DateTime(timezone=True)` | From mixin |
| `updated_at` | `DateTime(timezone=True)` | From mixin |

#### `KnowledgeItem` → table `knowledge_items`

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | `Integer` | Primary key |
| `project_id` | `Integer` | Foreign key to `projects.id`, nullable |
| `title` | `String(300)` | Non-nullable |
| `content` | `Text` | Non-nullable |
| `status` | `String(50)` | Default `"draft"`, non-nullable |
| `source_type` | `String(100)` | Nullable |
| `source_reference` | `Text` | Nullable |
| `created_at` | `DateTime(timezone=True)` | From mixin |
| `updated_at` | `DateTime(timezone=True)` | From mixin |

#### `ActivityLog` → table `activity_logs`

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | `Integer` | Primary key |
| `action` | `String(200)` | Non-nullable |
| `entity_type` | `String(100)` | Nullable |
| `entity_id` | `String(100)` | Nullable |
| `details` | `Text` | Nullable |
| `created_at` | `DateTime(timezone=True)` | From mixin |
| `updated_at` | `DateTime(timezone=True)` | From mixin |

#### `SystemSetting` → table `system_settings`

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | `Integer` | Primary key |
| `key` | `String(200)` | Unique, non-nullable |
| `value` | `Text` | Nullable |
| `description` | `Text` | Nullable |
| `created_at` | `DateTime(timezone=True)` | From mixin |
| `updated_at` | `DateTime(timezone=True)` | From mixin |

### Relationships

- Only one explicit relationship exists: `KnowledgeItem.project_id` → `projects.id`.
- No ORM `relationship()` attributes are defined, so back-references are not available.

### Tables known to SQLAlchemy metadata

Verified via `.venv/bin/python -c "from advancore.models import Base; [print(t.name) for t in Base.metadata.sorted_tables]"`:

- `activity_logs`
- `projects`
- `system_settings`
- `knowledge_items`

---

## 7. Database Initialization / Migration Approach

- **Current approach:** `Base.metadata.create_all(bind=engine)` in `initialize_database()`.
- **Migration framework:** None.
- **Implication:** Schema creation is implicit and additive only. There is no versioning, rollback, or safe evolution path once production data exists.
- **Risk level:** Medium for future production use; low for current local development.

---

## 8. Existing Modules and Maturity

| Module | Maturity | Assessment |
|--------|----------|------------|
| Streamlit app shell | Functional | Navigation works; page wiring is clean. |
| Dashboard page | Functional | Displays status and DB connectivity. |
| Knowledge Hub, Projects, AI Center, Activity Log, Settings | Skeleton/Placeholder | No business logic or persistence. |
| Database service | Functional but minimal | Engine + connectivity test only. |
| Models | Foundation | Well-structured, consistent `TimestampMixin`, but no relationships beyond one FK. |
| Tests | Absent | `tests/` contains only an empty `_init_.py` with a non-standard name. |
| Documentation areas | Empty placeholders | READMEs exist; no approved architecture, business rules, or decisions yet. |

---

## 9. Configuration / Environment Requirements

- **Required environment variable:** `DATABASE_URL`.
- **Loader:** `python-dotenv` reads `.env` at service import time.
- **Verified:** `.env` exists locally and `DATABASE_URL` is configured (`load_dotenv()` returns `True`).
- **Docker:** `docker-compose.yml` provides a local PostgreSQL 16 container:
  - Database: `advancore`
  - User: `advancore`
  - Password: `advancore_local_dev` (hard-coded for local development only)
  - Port: `5432`
- **Pyright:** `pyrightconfig.json` points to `.venv` for type-checking.
- **Important:** The `.env` file is listed in `.gitignore` and is not tracked by Git.

### Diagnostic results

| Check | Command | Result |
|-------|---------|--------|
| DATABASE_URL configured | `.venv/bin/python -c load_dotenv()` | `True` |
| Docker daemon running | `docker ps` | **Not running** |
| Database reachable | `test_database_connection()` | **False** (expected because Docker is not running) |
| Code compiles | `python -m py_compile ...` | Success |

---

## 10. Tests and Coverage Gaps

- **Test runner:** pytest is installed in the host Anaconda environment but **not in `.venv`**.
- **Test files:** Only `tests/_init_.py` exists.
  - **Note:** The file is named `_init_.py` (single leading/trailing underscore), not the standard `__init__.py`.
  - It is empty.
- **Test coverage:** 0%.
- **Coverage gaps:**
  - No unit tests for models.
  - No tests for `database.py` connection or initialization.
  - No tests for page `render()` functions.
  - No integration tests for Streamlit or database flow.

---

## 11. Duplicated, Obsolete, or Suspicious Code

- **No duplicated code** found.
- **No obsolete imports** found.
- **Suspicious findings:**
  1. `tests/_init_.py` non-standard name may prevent Python from treating `tests/` as a package. This is likely a typo for `__init__.py`.
  2. `advancore/__init__.py`, `advancore/pages/__init__.py`, and `advancore/services/__init__.py` are empty. This is acceptable but means no package-level exports are defined.
  3. `docker-compose.yml` contains a hard-coded local password. **FACT:** This is acceptable for local development only. **PROPOSAL:** Ensure production deployment uses injected secrets, not this file.

---

## 12. Security Risks

| Risk | Severity | Notes |
|------|----------|-------|
| `.env` is gitignored but exists locally | Low | Confirmed `.env` is not tracked (`git status --short` clean). |
| Hard-coded database password in `docker-compose.yml` | Low for local; **High if reused in production** | Password `advancore_local_dev` is clearly meant for local development. |
| No secrets management strategy | Medium | No Vault, AWS Secrets Manager, or similar abstraction; no production deployment path defined. |
| No input validation | Medium | Placeholder pages do not yet accept input; future CRUD pages will need validation. |
| Database initialized via `create_all()` | Low-Medium | No migration control; accidental schema changes could be destructive. |
| Minimal tests | Low-Medium | Agents making future changes have no automated safety net. |

**No credentials or secrets were committed to Git.**

---

## 13. Recommended Next Technical Sequence

Based on the audit, the smallest safe sequence for the next phase is:

1. **Fix the test package name** — rename `tests/_init_.py` to `tests/__init__.py` and install pytest in `.venv`.
2. **Add baseline tests** — model instantiation and database service smoke tests.
3. **Introduce a migration strategy** — evaluate Alembic and create an initial baseline migration before significant schema growth.
4. **Decide on session/CRUD patterns** — establish a repository or service pattern before building real pages.
5. **Implement the first business module** only after the above foundations are in place.

This preserves the current working application while adding the safety rails needed for larger agent-assisted changes.

---

## 14. Reasoning Labels

### FACT

- The repository contains 4 SQLAlchemy models: `Project`, `KnowledgeItem`, `ActivityLog`, `SystemSetting`.
- The only functional UI page is `dashboard.py`; the other five pages are placeholders.
- `initialize_database()` uses `Base.metadata.create_all()`; no migration tool is in use.
- `tests/_init_.py` is empty and has a non-standard filename.
- pytest is not installed in `.venv`.
- `DATABASE_URL` is configured in `.env`; Docker is not running, so the database is currently unreachable.
- The application code compiles without errors.
- `.env` is gitignored and not tracked by Git.

### INFERENCE

- The codebase is at v0.1 / Gate 0 foundation stage.
- Test coverage should be added before agents make larger autonomous changes.
- A migration framework should be introduced before production schema growth.

### PROPOSAL

- Rename `tests/_init_.py` to `tests/__init__.py`.
- Add pytest to `requirements.txt` and `.venv`.
- Evaluate Alembic for migration management.
- Establish a repository/session pattern before expanding CRUD features.
