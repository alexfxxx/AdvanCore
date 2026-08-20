"""Safe, read-only Git introspection for the local agent runner."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


class GitError(Exception):
    """Raised when a safe Git read operation fails."""


@dataclass(frozen=True)
class GitInfo:
    """Read-only snapshot of the repository state."""

    repo_root: Path
    current_branch: str
    head_sha: str
    is_clean: bool
    status_lines: list[str]


def _run_git(args: list[str], cwd: Path | None = None) -> str:
    """Run a Git command safely and return stdout text.

    The command is passed as an argument array (no shell). Only read-only
    operations are permitted by this module.
    """
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def get_git_info(cwd: Path | None = None) -> GitInfo:
    """Inspect the repository at *cwd* and return a ``GitInfo`` snapshot.

    Raises:
        GitError: if the working directory is not inside a Git repository or
            one of the safe read commands fails.
    """
    repo_root = Path(_run_git(["rev-parse", "--show-toplevel"], cwd=cwd).strip())
    current_branch = _run_git(["branch", "--show-current"], cwd=repo_root).strip()
    head_sha = _run_git(["rev-parse", "HEAD"], cwd=repo_root).strip()
    status_output = _run_git(["status", "--porcelain"], cwd=repo_root)
    status_lines = [line for line in status_output.splitlines() if line.strip()]

    return GitInfo(
        repo_root=repo_root,
        current_branch=current_branch,
        head_sha=head_sha,
        is_clean=len(status_lines) == 0,
        status_lines=status_lines,
    )
