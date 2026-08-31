# AdvanCore Master Specification

## Vision
AdvanCore is the central business intelligence, operations and AI-orchestration platform for the Advan ecosystem. Its long-term operating model is human-governed automation: software agents perform bounded work, the platform records decisions and outcomes, and humans handle approvals, exceptions and material business judgment.

## Current foundation
The current repository is a Python platform with a FastAPI-served HTML/CSS/JavaScript primary interface, a temporary Streamlit admin/editing interface, PostgreSQL operational storage, SQLAlchemy models, Docker support and GitHub version control.

## Core platform domains
Foundation modules:
- Executive Dashboard
- Knowledge Hub
- Projects
- AI Center
- Activity Log
- Settings

Planned business domains may include:
- Customer and Contract Management
- Transport Operations
- Routes and Stops
- Driver / Attendant Management
- Fleet Management
- Fuel Intelligence
- Maintenance
- Purchase Order Monitoring
- Payroll
- Finance and Invoicing
- Profitability
- Alerts and Exceptions
- AI Orchestration / Agent Actions

## Architectural principles
1. PostgreSQL stores operational data.
2. GitHub stores approved code, schema history, documentation and agent-control artifacts.
3. Modules should be independently testable and connected through explicit interfaces.
4. Business rules must be traceable and configurable where practical.
5. AI-generated knowledge remains draft until approved.
6. High-impact actions require explicit approval boundaries.
7. Build incrementally; do not attempt a monolithic ERP rewrite.
8. Every automated action should eventually be auditable.

## Agent operating model
Owner/domain expert -> Architect/reviewer -> Task specification -> Build agent(s) -> Tests -> Review -> Approval -> Merge/deploy.

The owner should provide business facts and decisions, not be required to write SQL, migrations or application code.

## Initial development objective
Before major new business modules are implemented, establish a reliable agent-controlled development workflow and audit the current repository. The first implementation task is therefore repository discovery and documentation, not feature expansion.

## Non-goals for the current phase
- Production deployment
- Autonomous merging to main
- Autonomous changes to commercial or compliance rules
- Broad rewrite of the existing application
- Production-data ingestion
