#!/bin/sh
set -eu

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
CHECK_ONLY=false

if [ "${1:-}" = "--check-only" ]; then
    CHECK_ONLY=true
elif [ "$#" -ne 0 ]; then
    echo "Usage: ./scripts/start-advancore.sh [--check-only]" >&2
    exit 2
fi

if ! command -v docker >/dev/null 2>&1; then
    echo "Docker is not available. Install or start Docker Desktop, then try again." >&2
    exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
    echo "Docker Compose is not available. Start or update Docker Desktop, then try again." >&2
    exit 1
fi
if [ ! -x "$PROJECT_ROOT/.venv/bin/python" ] || \
   [ ! -x "$PROJECT_ROOT/.venv/bin/streamlit" ] || \
   [ ! -x "$PROJECT_ROOT/.venv/bin/alembic" ]; then
    echo "The local Python environment is not ready. Follow the README setup once, then retry." >&2
    exit 1
fi
if [ ! -f "$PROJECT_ROOT/.env.example" ]; then
    echo "The safe local environment template is missing." >&2
    exit 1
fi

ENV_FILE="$PROJECT_ROOT/.env"
if [ ! -e "$ENV_FILE" ]; then
    ENV_FILE="$PROJECT_ROOT/.env.example"
fi
if [ -L "$ENV_FILE" ] || [ ! -f "$ENV_FILE" ]; then
    echo "The local development settings path is unsafe." >&2
    exit 1
fi
DATABASE_LINE_COUNT=$(grep -c '^DATABASE_URL=' "$ENV_FILE" || true)
if [ "$DATABASE_LINE_COUNT" -ne 1 ]; then
    echo "The local database setting is missing or ambiguous." >&2
    exit 1
fi
DATABASE_URL=$(sed -n 's/^DATABASE_URL=//p' "$ENV_FILE")
APPROVED_LOCAL_DATABASE_URL='postgresql+psycopg://advancore:advancore_local_dev@localhost:5432/advancore'
if [ "$DATABASE_URL" != "$APPROVED_LOCAL_DATABASE_URL" ]; then
    echo "Startup is limited to the approved loopback development database." >&2
    exit 1
fi

if [ "$CHECK_ONLY" = true ]; then
    echo "AdvanCore local prerequisites are ready."
    exit 0
fi

if [ ! -f "$PROJECT_ROOT/.env" ]; then
    cp "$PROJECT_ROOT/.env.example" "$PROJECT_ROOT/.env"
    chmod 600 "$PROJECT_ROOT/.env"
    echo "Created the local development settings file."
fi

cd "$PROJECT_ROOT"
docker compose up -d postgres
attempt=0
until docker compose exec -T postgres pg_isready -U advancore -d advancore >/dev/null 2>&1; do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge 30 ]; then
        echo "PostgreSQL did not become ready within 30 seconds. No migration was run." >&2
        exit 1
    fi
    sleep 1
done
export DATABASE_URL
"$PROJECT_ROOT/.venv/bin/alembic" upgrade head
echo "AdvanCore is starting. Keep this window open while using the app."
exec "$PROJECT_ROOT/.venv/bin/streamlit" run "$PROJECT_ROOT/app.py"
