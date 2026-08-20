# AdvanCore Agent Development Constitution

## Purpose
AdvanCore is an AI-assisted business intelligence and transport operations platform. AI agents may analyse, design, code, test and document the platform only within approved task scope.

## Source of truth
- GitHub is the source of truth for code, schema, migrations, tests, architecture decisions and approved knowledge.
- PostgreSQL is the operational database.
- Never use GitHub files as a production operational database.

## Mandatory workflow
Before implementing any feature:
1. Read this file and the relevant task file.
2. Inspect the existing implementation and dependencies.
3. Check whether equivalent functionality already exists.
4. Produce an implementation plan.
5. Implement only approved scope.
6. Run relevant tests.
7. Fix failures caused by the change.
8. Document material architecture/database changes.
9. Produce a completion report.

## Development rules
- Preserve working functionality unless the task explicitly authorises change.
- Never perform broad rewrites just because another architecture is preferred.
- Never hard-code customer-specific rules when a configurable design is appropriate.
- Keep modules independent but interoperable.
- Prefer small, reversible changes.
- Do not commit secrets, credentials, tokens or production data.

## Database rules
- Structural changes must be implemented through migrations once migrations are introduced.
- Never silently delete tables, columns or relationships.
- Never destroy production data.
- Never rewrite migration history after release.
- Every major entity should normally include a unique identifier, created timestamp, updated timestamp and status where appropriate.

## Reasoning labels
Agents must distinguish:
- FACT: confirmed requirement or repository fact.
- ASSUMPTION: unconfirmed but temporarily necessary belief.
- INFERENCE: conclusion derived from available evidence.
- PROPOSAL: suggested change requiring approval.

Never promote an assumption or proposal into an official business rule without approval.

## Singapore compliance
AdvanCore may touch PDPA, MOM, IRAS, GST, LTA, employment, fleet, passenger and school-transport requirements. Agents must flag compliance points for verification and must not invent legal requirements.

## Agent authority
Agents MAY inspect files, propose architecture, create scoped code, refactor within approved scope, create tests, create migrations, document changes and investigate errors.

Agents MAY NOT independently delete production data, deploy to production, expose secrets, change commercial rules, change compliance rules, merge major architecture changes, or approve their own critical work.

## Completion report
Every completed task must report:
- Implemented
- Files changed
- Database changes
- Tests executed and results
- Assumptions
- Risks / unresolved issues
- Decisions required
- Recommended next step
