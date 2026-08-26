"""Resolve only the canonical AdvanCore local PostgreSQL container."""

from __future__ import annotations

from pathlib import Path
import re
import subprocess
from typing import Callable


APPROVED_COMPOSE_PROJECT = "advancore-local"
APPROVED_COMPOSE_SERVICE = "postgres"
APPROVED_POSTGRES_IMAGE = "postgres:16"
APPROVED_POSTGRES_VOLUME = "advancore_advancore_postgres_data"
_CONTAINER_ID = re.compile(r"[0-9a-f]{12,64}")
_INSPECT_FORMAT = (
    '{{ index .Config.Labels "com.docker.compose.project" }}|'
    '{{ index .Config.Labels "com.docker.compose.service" }}|'
    "{{ .Config.Image }}|"
    '{{ range .Mounts }}{{ if eq .Destination "/var/lib/postgresql/data" }}'
    "{{ .Name }}{{ end }}{{ end }}"
)


class LocalPostgresContainerError(RuntimeError):
    """Raised when the canonical local database container cannot be proven."""


def _run_bounded(
    command_runner: Callable[..., subprocess.CompletedProcess],
    command: list[str],
    repository_root: Path,
) -> subprocess.CompletedProcess:
    try:
        return command_runner(
            command,
            cwd=repository_root,
            env={"LC_ALL": "C"},
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise LocalPostgresContainerError(
            "The canonical local PostgreSQL container is unavailable."
        ) from exc


def resolve_local_postgres_container(
    repository_root: Path,
    docker: str,
    expected_port: int,
    command_runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> str:
    """Return one container ID only after identity, volume, and port checks."""
    if (
        not isinstance(docker, str)
        or not Path(docker).is_absolute()
        or type(expected_port) is not int
        or not 1 <= expected_port <= 65535
    ):
        raise LocalPostgresContainerError(
            "The canonical local PostgreSQL container is unavailable."
        )
    root = Path(repository_root).resolve()
    listed = _run_bounded(
        command_runner,
        [
            docker,
            "ps",
            "--filter",
            f"label=com.docker.compose.project={APPROVED_COMPOSE_PROJECT}",
            "--filter",
            f"label=com.docker.compose.service={APPROVED_COMPOSE_SERVICE}",
            "--filter",
            "status=running",
            "--format",
            "{{.ID}}",
        ],
        root,
    )
    candidates = [
        line.strip() for line in (listed.stdout or "").splitlines() if line.strip()
    ]
    if (
        listed.returncode != 0
        or len(candidates) != 1
        or not _CONTAINER_ID.fullmatch(candidates[0])
    ):
        raise LocalPostgresContainerError(
            "The canonical local PostgreSQL container is unavailable."
        )
    container_id = candidates[0]

    inspected = _run_bounded(
        command_runner,
        [docker, "inspect", "--format", _INSPECT_FORMAT, container_id],
        root,
    )
    identity = (inspected.stdout or "").strip().split("|")
    if inspected.returncode != 0 or identity != [
        APPROVED_COMPOSE_PROJECT,
        APPROVED_COMPOSE_SERVICE,
        APPROVED_POSTGRES_IMAGE,
        APPROVED_POSTGRES_VOLUME,
    ]:
        raise LocalPostgresContainerError(
            "The canonical local PostgreSQL container identity is invalid."
        )

    published = _run_bounded(
        command_runner,
        [docker, "port", container_id, "5432/tcp"],
        root,
    )
    bindings = [
        line.strip() for line in (published.stdout or "").splitlines() if line.strip()
    ]
    if published.returncode != 0 or bindings != [f"127.0.0.1:{expected_port}"]:
        raise LocalPostgresContainerError(
            "The canonical local PostgreSQL container port is invalid."
        )
    return container_id
