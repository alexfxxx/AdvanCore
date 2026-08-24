"""Controller-owned standing authority for routine unattended actions.

This boundary records owner-supplied routine authority.  It never creates task,
implementation, merge, deployment, credential, or business-rule approval.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import pwd
import re
import stat
import subprocess
import sys
import tempfile
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit, urlunsplit


STANDING_AUTHORITY_SCHEMA = "advancore-standing-authority-v1"
MAX_AUTHORITY_TASKS = 10
MAX_AUTHORITY_HOURS = 24
MAX_AUTHORITY_USES = 200
_TASK_ID_RE = re.compile(r"^TASK-[0-9]{3,6}$")
_BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,119}$")


class StandingAuthorityError(ValueError):
    """Raised when routine authority is absent, invalid, or insufficient."""


class RoutineAction(str, Enum):
    """Actions that cannot spend owner/controller decision authority."""

    RUN_WORKER = "run-worker"
    RUN_TESTS = "run-tests"
    BOUNDED_REPAIR = "bounded-repair"
    INDEPENDENT_REVIEW = "independent-review"
    APPROVED_FALLBACK = "approved-fallback"
    UPDATE_FEATURE_BRANCH = "update-feature-branch"
    UPDATE_PR = "update-pr"
    REPORT_EXCEPTION = "report-exception"


@dataclass(frozen=True)
class StandingAuthority:
    schema_version: str
    authorization_id: str
    repository_id: str
    issued_at: str
    expires_at: str
    branch: str
    task_ids: tuple[str, ...]
    allowed_actions: tuple[str, ...]
    max_uses: int
    uses: int
    source: str


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def default_standing_authority_dir() -> Path:
    """Return one OS-account-wide controller authority directory."""
    account_home = Path(pwd.getpwuid(os.getuid()).pw_dir).resolve()
    if sys.platform == "darwin":
        root = account_home / "Library" / "Application Support" / "AdvanCore"
    else:
        root = account_home / ".local" / "state" / "advancore"
    return root / "standing-authority"


def _timestamp(value: str, label: str) -> datetime:
    if not isinstance(value, str) or len(value) > 40:
        raise StandingAuthorityError(f"invalid {label}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise StandingAuthorityError(f"invalid {label}") from exc
    if parsed.tzinfo is None:
        raise StandingAuthorityError(f"invalid {label}")
    return parsed.astimezone(timezone.utc)


def _canonical(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class StandingAuthorityService:
    """Record and consume exact routine authority under an OS-owned boundary."""

    def __init__(
        self,
        repo_root: Path,
        state_dir: Path | None = None,
        now_provider: Callable[[], datetime] = _utc_now,
    ):
        self.repo_root = repo_root.resolve(strict=True)
        self.repository_id = self._repository_identity()
        self.state_dir = (state_dir or default_standing_authority_dir()).resolve()
        self.now_provider = now_provider

    def _git(self, *args: str) -> str:
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise StandingAuthorityError("repository identity is unavailable") from exc
        if result.returncode != 0 or not result.stdout.strip():
            raise StandingAuthorityError("repository identity is unavailable")
        return result.stdout.strip()

    @staticmethod
    def _normalized_remote(value: str) -> str:
        """Remove credentials and presentation differences from one Git remote."""
        if "://" in value:
            parsed = urlsplit(value)
            if not parsed.hostname:
                raise StandingAuthorityError("repository remote is invalid")
            host = parsed.hostname.lower()
            if parsed.port:
                host = f"{host}:{parsed.port}"
            path = parsed.path.rstrip("/")
            if path.endswith(".git"):
                path = path[:-4]
            return urlunsplit((parsed.scheme.lower(), host, path, "", ""))
        match = re.fullmatch(r"(?:[^@/:]+@)?([^:]+):(.+)", value)
        if match:
            path = match.group(2).rstrip("/")
            if path.endswith(".git"):
                path = path[:-4]
            return f"ssh://{match.group(1).lower()}/{path}"
        path = Path(value).expanduser().resolve()
        return f"file://{path}"

    def _repository_identity(self) -> str:
        top = Path(self._git("rev-parse", "--show-toplevel")).resolve(strict=True)
        if top != self.repo_root:
            raise StandingAuthorityError("repository root is invalid")
        common_value = Path(self._git("rev-parse", "--git-common-dir"))
        common_dir = (
            common_value if common_value.is_absolute() else self.repo_root / common_value
        ).resolve(strict=True)
        info = common_dir.stat()
        remote = self._normalized_remote(self._git("remote", "get-url", "origin"))
        material = f"{info.st_dev}:{info.st_ino}:{common_dir}:{remote}".encode("utf-8")
        return hashlib.sha256(material).hexdigest()

    @property
    def authority_path(self) -> Path:
        return self.state_dir / "active.json"

    @property
    def lock_path(self) -> Path:
        return self.state_dir / "authority.lock"

    def _ensure_dir(self) -> None:
        self.state_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
        if self.state_dir.is_symlink():
            raise StandingAuthorityError("standing authority path is unsafe")
        info = self.state_dir.stat()
        if info.st_uid != os.getuid() or info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise StandingAuthorityError("standing authority path is unsafe")
        os.chmod(self.state_dir, 0o700)

    def _lock(self):
        self._ensure_dir()
        handle = self.lock_path.open("a+", encoding="utf-8")
        os.chmod(self.lock_path, 0o600)
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        return handle

    def _write(self, authority: StandingAuthority) -> None:
        temporary: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=self.state_dir, prefix=".authority-", delete=False
            ) as handle:
                temporary = handle.name
                os.chmod(temporary, 0o600)
                json.dump(asdict(authority), handle, sort_keys=True, separators=(",", ":"))
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.authority_path)
            os.chmod(self.authority_path, 0o600)
        except OSError as exc:
            if temporary:
                Path(temporary).unlink(missing_ok=True)
            raise StandingAuthorityError("cannot write standing authority") from exc

    def _load(self) -> StandingAuthority:
        path = self.authority_path
        if path.is_symlink() or not path.is_file():
            raise StandingAuthorityError("standing authority is unavailable")
        info = path.stat()
        if info.st_uid != os.getuid() or info.st_nlink != 1 or info.st_mode & 0o077:
            raise StandingAuthorityError("standing authority is unsafe")
        try:
            raw = path.read_text(encoding="utf-8")
            if len(raw.encode("utf-8")) > 16 * 1024:
                raise StandingAuthorityError("standing authority is invalid")
            data = json.loads(raw)
            data["task_ids"] = tuple(data["task_ids"])
            data["allowed_actions"] = tuple(data["allowed_actions"])
            authority = StandingAuthority(**data)
            self._validate(authority)
        except (
            OSError,
            UnicodeError,
            ValueError,
            RecursionError,
            KeyError,
            TypeError,
            StandingAuthorityError,
        ) as exc:
            raise StandingAuthorityError("standing authority is invalid") from exc
        return authority

    def _validate(self, authority: StandingAuthority) -> None:
        string_fields = (
            authority.schema_version,
            authority.authorization_id,
            authority.repository_id,
            authority.issued_at,
            authority.expires_at,
            authority.branch,
            authority.source,
        )
        if not all(isinstance(value, str) for value in string_fields):
            raise StandingAuthorityError("standing authority is invalid")
        if not isinstance(authority.task_ids, tuple) or not all(
            isinstance(value, str) for value in authority.task_ids
        ):
            raise StandingAuthorityError("standing authority task scope is invalid")
        if not isinstance(authority.allowed_actions, tuple) or not all(
            isinstance(value, str) for value in authority.allowed_actions
        ):
            raise StandingAuthorityError("standing authority action scope is invalid")
        if not isinstance(authority.max_uses, int) or isinstance(authority.max_uses, bool):
            raise StandingAuthorityError("standing authority usage limit is invalid")
        if not isinstance(authority.uses, int) or isinstance(authority.uses, bool):
            raise StandingAuthorityError("standing authority usage is invalid")
        if authority.schema_version != STANDING_AUTHORITY_SCHEMA:
            raise StandingAuthorityError("standing authority is invalid")
        try:
            if str(uuid.UUID(authority.authorization_id)) != authority.authorization_id:
                raise ValueError
        except (ValueError, AttributeError) as exc:
            raise StandingAuthorityError("standing authority is invalid") from exc
        if not re.fullmatch(r"[0-9a-f]{64}", authority.repository_id):
            raise StandingAuthorityError("standing authority repository is invalid")
        issued = _timestamp(authority.issued_at, "issued_at")
        expires = _timestamp(authority.expires_at, "expires_at")
        if expires <= issued or expires - issued > timedelta(hours=MAX_AUTHORITY_HOURS):
            raise StandingAuthorityError("standing authority duration is invalid")
        if not _BRANCH_RE.fullmatch(authority.branch) or authority.branch in {"main", "master"}:
            raise StandingAuthorityError("standing authority branch is invalid")
        if not 1 <= len(authority.task_ids) <= MAX_AUTHORITY_TASKS:
            raise StandingAuthorityError("standing authority task scope is invalid")
        if tuple(sorted(set(authority.task_ids))) != authority.task_ids or not all(
            _TASK_ID_RE.fullmatch(task_id) for task_id in authority.task_ids
        ):
            raise StandingAuthorityError("standing authority task scope is invalid")
        allowed = {item.value for item in RoutineAction}
        if not authority.allowed_actions or set(authority.allowed_actions) - allowed:
            raise StandingAuthorityError("standing authority action scope is invalid")
        if tuple(sorted(set(authority.allowed_actions))) != authority.allowed_actions:
            raise StandingAuthorityError("standing authority action scope is invalid")
        if not 1 <= authority.max_uses <= MAX_AUTHORITY_USES:
            raise StandingAuthorityError("standing authority usage limit is invalid")
        if not 0 <= authority.uses <= authority.max_uses:
            raise StandingAuthorityError("standing authority usage is invalid")
        if authority.source != "owner-explicit":
            raise StandingAuthorityError("standing authority source is invalid")

    def record(
        self,
        *,
        task_ids: list[str],
        branch: str,
        allowed_actions: list[RoutineAction | str],
        expires_at: datetime,
        max_uses: int,
        owner_confirmed: bool,
    ) -> StandingAuthority:
        """Record one exact owner-supplied routine grant."""
        if owner_confirmed is not True:
            raise StandingAuthorityError("explicit owner confirmation is required")
        now = self.now_provider().astimezone(timezone.utc)
        authority = StandingAuthority(
            schema_version=STANDING_AUTHORITY_SCHEMA,
            authorization_id=str(uuid.uuid4()),
            repository_id=self.repository_id,
            issued_at=_canonical(now),
            expires_at=_canonical(expires_at),
            branch=branch,
            task_ids=tuple(sorted(set(task_ids))),
            allowed_actions=tuple(
                sorted({item.value if isinstance(item, RoutineAction) else str(item) for item in allowed_actions})
            ),
            max_uses=max_uses,
            uses=0,
            source="owner-explicit",
        )
        self._validate(authority)
        lock = self._lock()
        try:
            self._write(authority)
        finally:
            lock.close()
        return authority

    def consume(self, task_id: str, branch: str, action: RoutineAction | str) -> StandingAuthority:
        """Validate and atomically count one routine action."""
        action_value = action.value if isinstance(action, RoutineAction) else str(action)
        lock = self._lock()
        try:
            authority = self._load()
            now = self.now_provider().astimezone(timezone.utc)
            if authority.repository_id != self.repository_id:
                raise StandingAuthorityError("standing authority does not cover this repository")
            if now < _timestamp(authority.issued_at, "issued_at") or now >= _timestamp(
                authority.expires_at, "expires_at"
            ):
                raise StandingAuthorityError("standing authority is expired")
            if task_id not in authority.task_ids or branch != authority.branch:
                raise StandingAuthorityError("standing authority does not cover this task and branch")
            if action_value not in authority.allowed_actions:
                raise StandingAuthorityError("standing authority does not cover this action")
            if authority.uses >= authority.max_uses:
                raise StandingAuthorityError("standing authority is exhausted")
            updated = StandingAuthority(**{**asdict(authority), "uses": authority.uses + 1})
            self._validate(updated)
            self._write(updated)
            return updated
        finally:
            lock.close()
