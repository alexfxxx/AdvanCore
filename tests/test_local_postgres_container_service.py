"""Fail-closed identity checks for the canonical local PostgreSQL container."""

from pathlib import Path
import subprocess

import pytest

from advancore.services.local_postgres_container_service import (
    LocalPostgresContainerError,
    resolve_local_postgres_container,
)


class Runner:
    def __init__(
        self,
        *,
        container_ids: str = "0123456789ab\n",
        identity: str = (
            "advancore-local|postgres|postgres:16|"
            "advancore_advancore_postgres_data\n"
        ),
        port: str = "127.0.0.1:5432\n",
    ):
        self.container_ids = container_ids
        self.identity = identity
        self.port = port
        self.calls = []

    def __call__(self, command, **kwargs):
        self.calls.append((command, kwargs))
        output = {
            "ps": self.container_ids,
            "inspect": self.identity,
            "port": self.port,
        }[command[1]]
        return subprocess.CompletedProcess(command, 0, output, "")


def test_canonical_container_requires_project_service_image_volume_and_loopback(tmp_path):
    runner = Runner()

    assert resolve_local_postgres_container(
        tmp_path, "/usr/local/bin/docker", 5432, runner
    ) == "0123456789ab"

    discovery = runner.calls[0][0]
    assert "label=com.docker.compose.project=advancore-local" in discovery
    assert "label=com.docker.compose.service=postgres" in discovery
    assert runner.calls[1][0][1] == "inspect"
    assert runner.calls[2][0] == [
        "/usr/local/bin/docker",
        "port",
        "0123456789ab",
        "5432/tcp",
    ]
    assert all(call[1]["env"] == {"LC_ALL": "C"} for call in runner.calls)


@pytest.mark.parametrize(
    ("runner", "message"),
    [
        (Runner(container_ids="0123456789ab\nabcdefabcdef\n"), "unavailable"),
        (
            Runner(
                identity=(
                    "unrelated|postgres|postgres:16|"
                    "advancore_advancore_postgres_data\n"
                )
            ),
            "identity",
        ),
        (
            Runner(
                identity="advancore-local|postgres|postgres:latest|other-volume\n"
            ),
            "identity",
        ),
        (Runner(port="0.0.0.0:5432\n"), "port"),
    ],
)
def test_ambiguous_or_unproven_container_fails_closed(tmp_path, runner, message):
    with pytest.raises(LocalPostgresContainerError, match=message):
        resolve_local_postgres_container(
            Path(tmp_path), "/usr/local/bin/docker", 5432, runner
        )

