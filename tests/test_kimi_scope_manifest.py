"""Contract tests for the controller-owned Kimi scope manifest."""

import json
import os
from pathlib import Path
import subprocess

import pytest

from advancore.agent_runner.kimi_scope_manifest import (
    KimiScopeManifestError,
    build_kimi_scope_manifest,
    prepare_kimi_scope_manifest,
    verify_kimi_scope_manifest,
)


def _worktree(tmp_path: Path) -> Path:
    root = tmp_path / "worktree"
    root.mkdir()
    subprocess.run(
        ["/usr/bin/git", "init", "-b", "task-147-scope"],
        cwd=root,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    (root / ".gitignore").write_text(
        ".kimi-scope\n.kimi-scope.lock\n.kimi-scope.*.tmp\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["/usr/bin/git", "add", ".gitignore"],
        cwd=root,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    subprocess.run(
        [
            "/usr/bin/git",
            "-c",
            "user.name=Test Owner",
            "-c",
            "user.email=owner@example.invalid",
            "commit",
            "-m",
            "initial",
        ],
        cwd=root,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return root


def test_prepare_verify_and_git_cleanliness(tmp_path):
    root = _worktree(tmp_path)
    manifest = prepare_kimi_scope_manifest(
        root, "TASK-147", ["tests/a.py", "advancore/a.py"]
    )

    assert manifest.allowed_paths == ("advancore/a.py", "tests/a.py")
    assert verify_kimi_scope_manifest(
        root, "TASK-147", ["advancore/a.py", "tests/a.py"]
    )
    status = subprocess.run(
        ["/usr/bin/git", "status", "--porcelain=v1"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    assert status.stdout == ""
    assert (root / ".kimi-scope").stat().st_mode & 0o077 == 0


def test_stale_or_changed_manifest_does_not_verify(tmp_path):
    root = _worktree(tmp_path)
    prepare_kimi_scope_manifest(root, "TASK-147", ["a.py"])

    assert not verify_kimi_scope_manifest(root, "TASK-148", ["a.py"])
    assert not verify_kimi_scope_manifest(root, "TASK-147", ["b.py"])


@pytest.mark.parametrize(
    "paths",
    [
        [],
        ["../a.py"],
        ["./a.py"],
        ["a/./b.py"],
        ["/tmp/a.py"],
        ["a//b.py"],
        ["a.py/"],
        ["*.py"],
        [".git/config"],
        ["nested/.git/config"],
        [".kimi-scope"],
        [".kimi-scope.lock"],
        [".kimi-scope.123.tmp"],
        ["Shared.py", "shared.py"],
    ],
)
def test_invalid_scope_input_fails_closed(paths):
    with pytest.raises(KimiScopeManifestError):
        build_kimi_scope_manifest("TASK-147", paths)


def test_invalid_task_and_non_string_paths_fail_closed():
    with pytest.raises(KimiScopeManifestError):
        build_kimi_scope_manifest("task-147", ["a.py"])
    with pytest.raises(KimiScopeManifestError):
        build_kimi_scope_manifest("TASK-147", [1])


def test_unsafe_existing_manifest_and_worktree_alias_fail_closed(tmp_path):
    root = _worktree(tmp_path)
    target = tmp_path / "target.json"
    target.write_text("{}", encoding="utf-8")
    (root / ".kimi-scope").symlink_to(target)
    with pytest.raises(KimiScopeManifestError):
        prepare_kimi_scope_manifest(root, "TASK-147", ["a.py"])

    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    with pytest.raises(KimiScopeManifestError):
        verify_kimi_scope_manifest(alias, "TASK-147", ["a.py"])


def test_malformed_oversized_and_fifo_manifest_fail_closed(tmp_path):
    root = _worktree(tmp_path)
    manifest = root / ".kimi-scope"
    manifest.write_text("[" * 1200, encoding="utf-8")
    manifest.chmod(0o600)
    with pytest.raises(KimiScopeManifestError):
        verify_kimi_scope_manifest(root, "TASK-147", ["a.py"])

    manifest.write_text("x" * (33 * 1024), encoding="utf-8")
    with pytest.raises(KimiScopeManifestError):
        verify_kimi_scope_manifest(root, "TASK-147", ["a.py"])

    manifest.unlink()
    os.mkfifo(manifest, mode=0o600)
    with pytest.raises(KimiScopeManifestError):
        verify_kimi_scope_manifest(root, "TASK-147", ["a.py"])


def test_manifest_contains_only_bounded_scope_metadata(tmp_path):
    root = _worktree(tmp_path)
    prepare_kimi_scope_manifest(root, "TASK-147", ["advancore/a.py"])
    raw = json.loads((root / ".kimi-scope").read_text(encoding="utf-8"))

    assert set(raw) == {"schema_version", "task_id", "allowed_paths"}
    for forbidden in ("prompt", "command", "credential", "output", "environment"):
        assert forbidden not in json.dumps(raw).lower()


def test_non_git_directory_and_boolean_schema_fail_closed(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(KimiScopeManifestError):
        prepare_kimi_scope_manifest(plain, "TASK-147", ["a.py"])

    root = _worktree(tmp_path)
    (root / ".kimi-scope").write_text(
        json.dumps(
            {
                "schema_version": True,
                "task_id": "TASK-147",
                "allowed_paths": ["a.py"],
            }
        ),
        encoding="utf-8",
    )
    (root / ".kimi-scope").chmod(0o600)
    with pytest.raises(KimiScopeManifestError):
        verify_kimi_scope_manifest(root, "TASK-147", ["a.py"])


def test_string_paths_duplicate_keys_and_scope_aliases_fail_closed(tmp_path):
    root = _worktree(tmp_path)
    manifest = root / ".kimi-scope"
    manifest.write_text(
        '{"schema_version":1,"task_id":"TASK-147",'
        '"allowed_paths":"ab"}',
        encoding="utf-8",
    )
    manifest.chmod(0o600)
    with pytest.raises(KimiScopeManifestError, match="JSON list"):
        verify_kimi_scope_manifest(root, "TASK-147", ["a", "b"])

    manifest.write_text(
        '{"schema_version":1,"schema_version":1,'
        '"task_id":"TASK-147","allowed_paths":["a.py"]}',
        encoding="utf-8",
    )
    with pytest.raises(KimiScopeManifestError, match="duplicate JSON keys"):
        verify_kimi_scope_manifest(root, "TASK-147", ["a.py"])

    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "alias").symlink_to(outside, target_is_directory=True)
    with pytest.raises(KimiScopeManifestError, match="symbolic-link alias"):
        prepare_kimi_scope_manifest(root, "TASK-147", ["alias/file.py"])

    first = root / "first.py"
    first.write_text("x\n", encoding="utf-8")
    os.link(first, root / "second.py")
    with pytest.raises(KimiScopeManifestError, match="file alias"):
        prepare_kimi_scope_manifest(
            root, "TASK-147", ["first.py", "second.py"]
        )
