# Start AdvanCore locally

From the repository, run:

```bash
./scripts/start-advancore.sh
```

The command checks Docker and the existing Python environment, creates the
local development settings file only when missing, starts PostgreSQL, applies
approved migrations and launches the app. It does not display credentials.

To check readiness without starting or changing anything:

```bash
./scripts/start-advancore.sh --check-only
```

Stop the app with Control-C. Stop the local database later with
`docker compose down`. Production deployment and production secrets are not
part of this command.

