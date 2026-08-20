"""Task-file discovery and parsing for the local agent runner."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# TASK-###-short-name.md
_TASK_FILENAME_RE = re.compile(r"^(TASK-\d+)-(.+)\.md$", re.IGNORECASE)

# STATUS: READY
_STATUS_LINE_RE = re.compile(r"^STATUS:\s*(\w+)", re.IGNORECASE)

# # TASK-### — Task Title
_TITLE_RE = re.compile(r"^#\s+(TASK-\d+)\s*[—–-]\s*(.+)$", re.IGNORECASE)

ALLOWED_STATUSES = {"READY", "REWORK"}


class TaskError(Exception):
    """Raised when a task file cannot be parsed or is invalid."""


@dataclass(frozen=True)
class Task:
    """A discovered task with parsed metadata."""

    task_id: str
    title: str
    status: str
    filename: str
    path: Path

    def __str__(self) -> str:
        return f"{self.task_id}: {self.title} ({self.status})"


def discover_tasks(tasks_dir: Path) -> list[Task]:
    """Return all parseable tasks in *tasks_dir*, sorted by filename."""
    tasks: list[Task] = []
    for path in sorted(tasks_dir.glob("TASK-*.md")):
        try:
            tasks.append(parse_task(path))
        except TaskError:
            # Skip malformed task files rather than failing the whole discovery.
            continue
    return tasks


def parse_task(path: Path) -> Task:
    """Parse a single task file and return a ``Task``.

    Raises:
        TaskError: if the filename or required metadata is missing/invalid.
    """
    filename = path.name
    match = _TASK_FILENAME_RE.match(filename)
    if not match:
        raise TaskError(f"Filename does not match TASK-###-name.md pattern: {filename}")

    task_id_from_filename = match.group(1).upper()
    text = path.read_text(encoding="utf-8")

    status: str | None = None
    title: str | None = None
    task_id: str | None = None

    for line in text.splitlines():
        if status is None:
            status_match = _STATUS_LINE_RE.match(line)
            if status_match:
                status = status_match.group(1).upper()

        if title is None and line.startswith("#"):
            title_match = _TITLE_RE.match(line)
            if title_match:
                task_id = title_match.group(1).upper()
                title = title_match.group(2).strip()

    if status is None:
        raise TaskError(f"No STATUS line found in {filename}")
    if title is None or task_id is None:
        raise TaskError(f"No title/ID found in {filename}")
    if task_id != task_id_from_filename:
        raise TaskError(
            f"Task ID mismatch in {filename}: "
            f"filename says {task_id_from_filename}, title says {task_id}"
        )

    return Task(
        task_id=task_id,
        title=title,
        status=status,
        filename=filename,
        path=path,
    )


def _candidate_paths(tasks_dir: Path, task_id: str) -> list[Path]:
    """Return all possible file paths for *task_id* under *tasks_dir*."""
    normalized = task_id.upper().strip()

    # Already a path to a task file.
    if normalized.endswith(".MD") or "/" in normalized or "\\" in normalized:
        candidate = tasks_dir / normalized
        if candidate.exists():
            return [candidate.resolve()]
        return []

    candidates: list[Path] = []

    # Exact filename match (e.g. TASK-005-name.md passed as the identifier).
    exact = tasks_dir / normalized
    if exact.exists() and exact.suffix.lower() == ".md":
        candidates.append(exact.resolve())

    # Standard glob pattern for the short ID.
    candidates.extend(sorted(tasks_dir.glob(f"{normalized}-*.md")))

    return candidates


def find_task(tasks_dir: Path, task_id: str) -> Task:
    """Find a task deterministically by ID or path.

    Raises:
        TaskError: if the task cannot be found or is ambiguous.
    """
    candidates = _candidate_paths(tasks_dir, task_id)

    if len(candidates) > 1:
        raise TaskError(
            f"Task identifier {task_id!r} is ambiguous: "
            f"{[p.name for p in candidates]}"
        )

    if len(candidates) == 1:
        return parse_task(candidates[0])

    # Fall back to full discovery for a plain ID.
    normalized = task_id.upper().strip()
    for task in discover_tasks(tasks_dir):
        if task.task_id == normalized:
            return task

    raise TaskError(f"Task {task_id!r} not found in {tasks_dir}")
