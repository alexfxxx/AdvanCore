"""Focused tests for safe legacy local-database consolidation."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
START_SCRIPT = REPOSITORY_ROOT / "scripts" / "start-advancore.sh"


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _local_startup_fixture(tmp_path: Path) -> tuple[Path, Path, dict[str, str]]:
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    (root / ".venv" / "bin").mkdir(parents=True)
    (root / "fake-bin").mkdir()
    shutil.copy2(START_SCRIPT, root / "scripts" / START_SCRIPT.name)
    shutil.copy2(REPOSITORY_ROOT / "docker-compose.yml", root / "docker-compose.yml")
    shutil.copy2(REPOSITORY_ROOT / ".env.example", root / ".env.example")
    (root / "app.py").write_text("", encoding="utf-8")

    log = tmp_path / "calls.log"
    tool_script = """#!/bin/sh
set -eu
printf '%s\\n' "$0 $*" >> "$ADVANCORE_TEST_LOG"
if [ "$(basename "$0")" = alembic ] && [ "${ADVANCORE_TEST_ALEMBIC_FAIL:-false}" = true ]; then
    exit 1
fi
exit 0
"""
    for tool in ("python", "alembic", "streamlit"):
        _write_executable(root / ".venv" / "bin" / tool, tool_script)

    docker_script = """#!/bin/sh
set -eu
printf 'docker %s\\n' "$*" >> "$ADVANCORE_TEST_LOG"
if [ "$*" = "--context default compose version" ]; then
    exit 0
fi
if [ "${1:-}" = "--context" ] && [ "${3:-}" = "inspect" ]; then
    if [ "${ADVANCORE_TEST_LEGACY_PRESENT:-true}" != true ]; then
        exit 1
    fi
    if [ "${4:-}" != "--format" ]; then
        exit 0
    fi
    case "${5:-}" in
        *compose.project*) printf '%s\\n' "${ADVANCORE_TEST_LEGACY_PROJECT:-advancore}" ;;
        *compose.service*) printf '%s\\n' "${ADVANCORE_TEST_LEGACY_SERVICE:-postgres}" ;;
        *Config.Image*) printf '%s\\n' "${ADVANCORE_TEST_LEGACY_IMAGE:-postgres:16}" ;;
        *Mounts*) printf '%s\\n' "${ADVANCORE_TEST_LEGACY_VOLUME:-advancore_advancore_postgres_data}" ;;
        *State.Running*) printf '%s\\n' "${ADVANCORE_TEST_LEGACY_RUNNING:-true}" ;;
        *) exit 2 ;;
    esac
    exit 0
fi
if [ "$*" = "--context default volume inspect advancore_advancore_postgres_data" ]; then
    if [ "${ADVANCORE_TEST_VOLUME_PRESENT:-true}" = true ]; then
        exit 0
    fi
    exit 1
fi
if [ "$*" = "--context default volume create advancore_advancore_postgres_data" ]; then
    printf '%s\\n' advancore_advancore_postgres_data
    exit 0
fi
case "$*" in
    *" compose "*" up -d postgres")
        if [ "${ADVANCORE_TEST_COMPOSE_UP_FAIL:-false}" = true ]; then
            exit 1
        fi
        exit 0
        ;;
    *" compose "*" exec -T postgres pg_isready -U advancore -d advancore") exit 0 ;;
    *" compose "*" down") exit 0 ;;
    "--context default stop advancore-postgres") exit 0 ;;
    "--context default start advancore-postgres") exit 0 ;;
esac
exit 2
"""
    _write_executable(root / "fake-bin" / "docker", docker_script)

    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{root / 'fake-bin'}:{environment['PATH']}",
            "ADVANCORE_TEST_LOG": str(log),
        }
    )
    return root, log, environment


def _run_startup(root: Path, environment: dict[str, str], *arguments: str):
    return subprocess.run(
        [str(root / "scripts" / "start-advancore.sh"), *arguments],
        cwd=root,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def test_compose_uses_loopback_and_shared_volume_without_fixed_container_name():
    compose_text = (REPOSITORY_ROOT / "docker-compose.yml").read_text(
        encoding="utf-8"
    )
    assert "container_name:" not in compose_text
    assert '"127.0.0.1:5432:5432"' in compose_text
    assert "external: true" in compose_text
    assert "name: advancore_advancore_postgres_data" in compose_text


def test_check_only_validates_legacy_without_changing_containers(tmp_path):
    root, log, environment = _local_startup_fixture(tmp_path)

    result = _run_startup(root, environment, "--check-only")

    assert result.returncode == 0
    assert "prerequisites are ready" in result.stdout
    calls = log.read_text(encoding="utf-8")
    assert "inspect --format" in calls
    assert " stop " not in calls
    assert " start " not in calls
    assert " up -d postgres" not in calls


def test_start_stops_verified_legacy_and_runs_canonical_service(tmp_path):
    root, log, environment = _local_startup_fixture(tmp_path)

    result = _run_startup(root, environment)

    assert result.returncode == 0, result.stderr
    calls = log.read_text(encoding="utf-8")
    assert calls.index("stop advancore-postgres") < calls.index("up -d postgres")
    assert "--project-name advancore-local" in calls
    assert ".venv/bin/alembic upgrade head" in calls
    assert ".venv/bin/streamlit run" in calls
    assert "--server.address 127.0.0.1" in calls
    assert "PRIMARY APP: http://127.0.0.1:8000" in result.stdout
    assert "Temporary admin/editing interface: http://127.0.0.1:8501" in result.stdout


def test_fresh_start_creates_shared_volume_before_compose(tmp_path):
    root, log, environment = _local_startup_fixture(tmp_path)
    environment["ADVANCORE_TEST_LEGACY_PRESENT"] = "false"
    environment["ADVANCORE_TEST_VOLUME_PRESENT"] = "false"

    result = _run_startup(root, environment)

    assert result.returncode == 0, result.stderr
    calls = log.read_text(encoding="utf-8")
    assert calls.index("volume create") < calls.index("up -d postgres")
    assert "stop advancore-postgres" not in calls


def test_incompatible_same_name_container_fails_without_mutation(tmp_path):
    root, log, environment = _local_startup_fixture(tmp_path)
    environment["ADVANCORE_TEST_LEGACY_PROJECT"] = "not-advancore"

    result = _run_startup(root, environment)

    assert result.returncode == 1
    assert "not the approved legacy AdvanCore database" in result.stderr
    calls = log.read_text(encoding="utf-8")
    assert " stop " not in calls
    assert " start " not in calls
    assert " up -d postgres" not in calls


def test_failed_canonical_start_restarts_previously_running_legacy(tmp_path):
    root, log, environment = _local_startup_fixture(tmp_path)
    environment["ADVANCORE_TEST_COMPOSE_UP_FAIL"] = "true"

    result = _run_startup(root, environment)

    assert result.returncode == 1
    assert "saved database volume was not changed" in result.stderr
    calls = log.read_text(encoding="utf-8")
    assert calls.index("stop advancore-postgres") < calls.index("up -d postgres")
    assert calls.index("up -d postgres") < calls.index("start advancore-postgres")
    assert ".venv/bin/alembic" not in calls


def test_failed_migration_stops_canonical_and_restores_legacy(tmp_path):
    root, log, environment = _local_startup_fixture(tmp_path)
    environment["ADVANCORE_TEST_ALEMBIC_FAIL"] = "true"

    result = _run_startup(root, environment)

    assert result.returncode == 1
    assert "migrations could not be applied" in result.stderr
    calls = log.read_text(encoding="utf-8")
    assert calls.index("up -d postgres") < calls.index(".venv/bin/alembic")
    assert calls.rindex("down") < calls.rindex("start advancore-postgres")
    assert ".venv/bin/streamlit" not in calls
