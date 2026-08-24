#!/bin/sh
set -eu

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
CHECK_ONLY=false
STOP_ONLY=false

if [ "$#" -gt 1 ]; then
    echo "Usage: ./scripts/start-advancore.sh [--check-only|--stop]" >&2
    exit 2
elif [ "${1:-}" = "--check-only" ]; then
    CHECK_ONLY=true
elif [ "${1:-}" = "--stop" ]; then
    STOP_ONLY=true
elif [ "$#" -ne 0 ]; then
    echo "Usage: ./scripts/start-advancore.sh [--check-only|--stop]" >&2
    exit 2
fi

if ! command -v docker >/dev/null 2>&1; then
    echo "Docker is not available. Install or start Docker Desktop, then try again." >&2
    exit 1
fi
unset COMPOSE_FILE COMPOSE_PROJECT_NAME COMPOSE_PROFILES DOCKER_HOST DOCKER_CONTEXT
unset DOCKER_TLS_VERIFY DOCKER_CERT_PATH DOCKER_CONFIG
if ! docker --context default compose version >/dev/null 2>&1; then
    echo "Docker Compose is not available. Start or update Docker Desktop, then try again." >&2
    exit 1
fi
if [ -L "$PROJECT_ROOT/docker-compose.yml" ] || [ ! -f "$PROJECT_ROOT/docker-compose.yml" ]; then
    echo "The local Docker Compose configuration is unsafe or missing." >&2
    exit 1
fi
compose() {
    docker --context default compose \
        --project-name advancore-local \
        --project-directory "$PROJECT_ROOT" \
        --env-file /dev/null \
        --file "$PROJECT_ROOT/docker-compose.yml" \
        "$@"
}

LEGACY_CONTAINER=advancore-postgres
LEGACY_PROJECT=advancore
LEGACY_SERVICE=postgres
LEGACY_IMAGE=postgres:16
LEGACY_VOLUME=advancore_advancore_postgres_data
LEGACY_WAS_RUNNING=false

legacy_exists() {
    docker --context default inspect "$LEGACY_CONTAINER" >/dev/null 2>&1
}

legacy_value() {
    docker --context default inspect --format "$1" "$LEGACY_CONTAINER"
}

validate_legacy_container() {
    legacy_project=$(legacy_value '{{ index .Config.Labels "com.docker.compose.project" }}')
    legacy_service=$(legacy_value '{{ index .Config.Labels "com.docker.compose.service" }}')
    legacy_image=$(legacy_value '{{ .Config.Image }}')
    legacy_volume=$(legacy_value '{{ range .Mounts }}{{ if eq .Destination "/var/lib/postgresql/data" }}{{ .Name }}{{ end }}{{ end }}')

    if [ "$legacy_project" != "$LEGACY_PROJECT" ] || \
       [ "$legacy_service" != "$LEGACY_SERVICE" ] || \
       [ "$legacy_image" != "$LEGACY_IMAGE" ] || \
       [ "$legacy_volume" != "$LEGACY_VOLUME" ]; then
        echo "A same-name Docker container exists but is not the approved legacy AdvanCore database. No container was changed." >&2
        exit 1
    fi
}

legacy_is_running() {
    [ "$(legacy_value '{{ .State.Running }}')" = true ]
}

ensure_canonical_volume() {
    if docker --context default volume inspect "$LEGACY_VOLUME" >/dev/null 2>&1; then
        return
    fi
    created_volume=$(docker --context default volume create "$LEGACY_VOLUME")
    if [ "$created_volume" != "$LEGACY_VOLUME" ]; then
        echo "The canonical local database volume could not be prepared safely." >&2
        exit 1
    fi
}

rollback_canonical_start() {
    compose down >/dev/null 2>&1 || true
    if [ "$LEGACY_WAS_RUNNING" = true ]; then
        docker --context default start "$LEGACY_CONTAINER" >/dev/null 2>&1 || true
    fi
}

if legacy_exists; then
    validate_legacy_container
fi

if [ "$STOP_ONLY" = true ]; then
    compose down
    if legacy_exists && legacy_is_running; then
        docker --context default stop "$LEGACY_CONTAINER" >/dev/null
    fi
    echo "AdvanCore local database stopped. Local data was kept."
    exit 0
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

ENV_TARGET="$PROJECT_ROOT/.env"
if [ -L "$ENV_TARGET" ]; then
    echo "The local development settings path is unsafe." >&2
    exit 1
fi
if [ -e "$ENV_TARGET" ] && [ ! -f "$ENV_TARGET" ]; then
    echo "The local development settings path is unsafe." >&2
    exit 1
fi
ENV_FILE="$ENV_TARGET"
if [ ! -f "$ENV_FILE" ]; then
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

if [ ! -f "$ENV_TARGET" ]; then
    umask 077
    if ! (set -C; : > "$ENV_TARGET") 2>/dev/null; then
        echo "The local development settings file could not be created safely." >&2
        exit 1
    fi
    cp "$PROJECT_ROOT/.env.example" "$ENV_TARGET"
    chmod 600 "$ENV_TARGET"
    echo "Created the local development settings file."
fi

cd "$PROJECT_ROOT"
ensure_canonical_volume
if legacy_exists && legacy_is_running; then
    docker --context default stop "$LEGACY_CONTAINER" >/dev/null
    LEGACY_WAS_RUNNING=true
    echo "Stopped the verified legacy database container. Its saved data was kept."
fi
if ! compose up -d postgres; then
    rollback_canonical_start
    echo "The canonical local database could not start. The saved database volume was not changed." >&2
    exit 1
fi
attempt=0
until compose exec -T postgres pg_isready -U advancore -d advancore >/dev/null 2>&1; do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge 30 ]; then
        rollback_canonical_start
        echo "PostgreSQL did not become ready within 30 seconds. No migration was run." >&2
        exit 1
    fi
    sleep 1
done
export DATABASE_URL
if ! "$PROJECT_ROOT/.venv/bin/alembic" upgrade head; then
    rollback_canonical_start
    echo "Approved database migrations could not be applied. The saved database volume was kept." >&2
    exit 1
fi
echo "AdvanCore is starting. Keep this window open while using the app."
exec "$PROJECT_ROOT/.venv/bin/streamlit" run "$PROJECT_ROOT/app.py" \
    --server.address 127.0.0.1
