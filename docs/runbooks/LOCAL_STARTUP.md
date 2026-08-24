# Start AdvanCore locally

From the repository, run:

```bash
./scripts/start-advancore.sh
```

The command checks Docker and the existing Python environment, creates the
local development settings file only when missing, starts PostgreSQL, applies
approved migrations and launches the app. It does not display credentials.

On a Mac with the older manually started `advancore-postgres` container, the
launcher verifies the expected Compose identity, PostgreSQL image and database
volume before changing anything. It then stops—but does not delete—the legacy
container and starts the canonical service against the same saved volume. If
canonical startup fails, it attempts to restart the previously running legacy
container. A same-name container with any unexpected identity fails closed.

The canonical PostgreSQL port and Streamlit app are bound to `127.0.0.1` only.
The preserved external data volume is
`advancore_advancore_postgres_data`. A fresh local installation creates that
volume before starting Compose.

To check readiness without starting or changing anything:

```bash
./scripts/start-advancore.sh --check-only
```

Stop the app with Control-C. Stop the matching local database later, without
deleting its saved data, with:

```bash
./scripts/start-advancore.sh --stop
```

Production deployment and production secrets are not part of these commands.
