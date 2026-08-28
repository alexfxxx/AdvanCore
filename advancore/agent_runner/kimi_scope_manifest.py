"""Controller-owned machine-readable scope manifest for a Kimi worktree."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import stat
from typing import Iterator


_TASK_ID = re.compile(r"^TASK-[0-9]{3}$")
_SAFE_PATH = re.compile(r"^[A-Za-z0-9_.@+/-]{1,200}$")
_MAX_PATHS = 64
_MAX_BYTES = 32 * 1024
_MANIFEST_NAME = ".kimi-scope"
_LOCK_NAME = ".kimi-scope.lock"


class KimiScopeManifestError(RuntimeError):
    """Raised when manifest input or worktree state is unsafe."""


@dataclass(frozen=True)
class KimiScopeManifest:
    schema_version: int
    task_id: str
    allowed_paths: tuple[str, ...]


def _validate_path(value: str) -> str:
    if not isinstance(value, str) or not _SAFE_PATH.fullmatch(value):
        raise KimiScopeManifestError("scope manifest path is invalid")
    raw_parts = value.split("/")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or value.endswith("/")
        or "" in raw_parts
        or "." in raw_parts
        or ".." in raw_parts
        or any(character in value for character in "*?[]{}")
    ):
        raise KimiScopeManifestError("scope manifest path is unsafe")
    return value


def _validate_manifest(manifest: KimiScopeManifest) -> KimiScopeManifest:
    if (
        isinstance(manifest.schema_version, bool)
        or not isinstance(manifest.schema_version, int)
        or manifest.schema_version != 1
        or not isinstance(manifest.task_id, str)
        or not _TASK_ID.fullmatch(manifest.task_id)
        or not isinstance(manifest.allowed_paths, tuple)
        or not 1 <= len(manifest.allowed_paths) <= _MAX_PATHS
    ):
        raise KimiScopeManifestError("scope manifest identity is invalid")
    paths = tuple(_validate_path(value) for value in manifest.allowed_paths)
    if paths != tuple(sorted(paths, key=str.casefold)):
        raise KimiScopeManifestError("scope manifest paths must be sorted")
    if len({value.casefold() for value in paths}) != len(paths):
        raise KimiScopeManifestError("scope manifest paths contain an alias")
    return KimiScopeManifest(1, manifest.task_id, paths)


def build_kimi_scope_manifest(
    task_id: str, allowed_paths: list[str] | tuple[str, ...]
) -> KimiScopeManifest:
    if not isinstance(allowed_paths, (list, tuple)):
        raise KimiScopeManifestError("scope manifest paths are invalid")
    try:
        paths = tuple(sorted(allowed_paths, key=str.casefold))
    except (AttributeError, TypeError) as exc:
        raise KimiScopeManifestError("scope manifest paths are invalid") from exc
    return _validate_manifest(KimiScopeManifest(1, task_id, paths))


def _open_worktree_root(path: Path) -> int:
    absolute = path.absolute()
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(absolute.anchor, flags)
    try:
        for part in absolute.parts[1:]:
            if part in {".", ".."}:
                raise KimiScopeManifestError("worktree path contains a dot segment")
            child = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        details = os.fstat(descriptor)
        if not stat.S_ISDIR(details.st_mode) or details.st_uid != os.getuid():
            raise KimiScopeManifestError("worktree root is unsafe")
        result = descriptor
        descriptor = -1
        return result
    except KimiScopeManifestError:
        raise
    except OSError as exc:
        raise KimiScopeManifestError("worktree root cannot be opened safely") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _validate_scope_locations(
    root_descriptor: int, paths: tuple[str, ...]
) -> None:
    identities: set[tuple[int, int]] = set()
    for value in paths:
        descriptor = os.dup(root_descriptor)
        try:
            parts = PurePosixPath(value).parts
            missing = False
            for index, part in enumerate(parts):
                try:
                    child = os.open(
                        part,
                        os.O_RDONLY
                        | getattr(os, "O_NOFOLLOW", 0)
                        | getattr(os, "O_NONBLOCK", 0),
                        dir_fd=descriptor,
                    )
                except FileNotFoundError:
                    missing = True
                    break
                details = os.fstat(child)
                if index < len(parts) - 1 and not stat.S_ISDIR(details.st_mode):
                    os.close(child)
                    raise KimiScopeManifestError(
                        "scope manifest parent path is unsafe"
                    )
                if index == len(parts) - 1 and not (
                    stat.S_ISREG(details.st_mode) or stat.S_ISDIR(details.st_mode)
                ):
                    os.close(child)
                    raise KimiScopeManifestError(
                        "scope manifest target path is unsafe"
                    )
                os.close(descriptor)
                descriptor = child
            if not missing:
                details = os.fstat(descriptor)
                identity = (details.st_dev, details.st_ino)
                if identity in identities:
                    raise KimiScopeManifestError(
                        "scope manifest paths contain a file alias"
                    )
                identities.add(identity)
        except KimiScopeManifestError:
            raise
        except OSError as exc:
            raise KimiScopeManifestError(
                "scope manifest path contains a symbolic-link alias"
            ) from exc
        finally:
            os.close(descriptor)


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise KimiScopeManifestError("scope manifest has duplicate JSON keys")
        result[key] = value
    return result


@contextmanager
def _locked_worktree(path: Path) -> Iterator[int]:
    root_descriptor: int | None = None
    lock_descriptor: int | None = None
    git_descriptor: int | None = None
    try:
        root_descriptor = _open_worktree_root(path)
        git_descriptor = os.open(
            ".git",
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0),
            dir_fd=root_descriptor,
        )
        git_details = os.fstat(git_descriptor)
        if (
            not (
                stat.S_ISREG(git_details.st_mode)
                or stat.S_ISDIR(git_details.st_mode)
            )
            or git_details.st_uid != os.getuid()
            or (stat.S_ISREG(git_details.st_mode) and git_details.st_nlink != 1)
        ):
            raise KimiScopeManifestError("worktree Git marker is unsafe")
        os.close(git_descriptor)
        git_descriptor = None
        lock_descriptor = os.open(
            _LOCK_NAME,
            os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=root_descriptor,
        )
        details = os.fstat(lock_descriptor)
        if (
            not stat.S_ISREG(details.st_mode)
            or details.st_uid != os.getuid()
            or details.st_nlink != 1
            or stat.S_IMODE(details.st_mode) & 0o077
        ):
            raise KimiScopeManifestError("scope manifest lock is unsafe")
        fcntl.flock(lock_descriptor, fcntl.LOCK_EX)
        yield root_descriptor
    except KimiScopeManifestError:
        raise
    except OSError as exc:
        raise KimiScopeManifestError("scope manifest lock failed") from exc
    finally:
        if git_descriptor is not None:
            os.close(git_descriptor)
        if lock_descriptor is not None:
            try:
                fcntl.flock(lock_descriptor, fcntl.LOCK_UN)
            except OSError:
                pass
            os.close(lock_descriptor)
        if root_descriptor is not None:
            os.close(root_descriptor)


def _read_unlocked(root_descriptor: int) -> KimiScopeManifest:
    descriptor: int | None = None
    try:
        descriptor = os.open(
            _MANIFEST_NAME,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0),
            dir_fd=root_descriptor,
        )
        details = os.fstat(descriptor)
        if (
            not stat.S_ISREG(details.st_mode)
            or details.st_uid != os.getuid()
            or details.st_nlink != 1
            or stat.S_IMODE(details.st_mode) & 0o077
            or details.st_size > _MAX_BYTES
        ):
            raise KimiScopeManifestError("scope manifest file is unsafe")
        chunks: list[bytes] = []
        remaining = _MAX_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, min(4096, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
        if len(content) > _MAX_BYTES:
            raise KimiScopeManifestError("scope manifest exceeds its size limit")
        raw = json.loads(
            content.decode("utf-8"), object_pairs_hook=_unique_json_object
        )
    except FileNotFoundError as exc:
        raise KimiScopeManifestError("scope manifest is missing") from exc
    except KimiScopeManifestError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise KimiScopeManifestError("scope manifest cannot be read") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if not isinstance(raw, dict) or set(raw) != {
        "schema_version",
        "task_id",
        "allowed_paths",
    }:
        raise KimiScopeManifestError("scope manifest shape is invalid")
    if not isinstance(raw["allowed_paths"], list):
        raise KimiScopeManifestError("scope manifest paths must be a JSON list")
    try:
        manifest = KimiScopeManifest(
            schema_version=raw["schema_version"],
            task_id=raw["task_id"],
            allowed_paths=tuple(raw["allowed_paths"]),
        )
    except (KeyError, TypeError) as exc:
        raise KimiScopeManifestError("scope manifest values are invalid") from exc
    validated = _validate_manifest(manifest)
    _validate_scope_locations(root_descriptor, validated.allowed_paths)
    return validated


def prepare_kimi_scope_manifest(
    worktree: Path, task_id: str, allowed_paths: list[str] | tuple[str, ...]
) -> KimiScopeManifest:
    manifest = build_kimi_scope_manifest(task_id, allowed_paths)
    payload = {
        "schema_version": manifest.schema_version,
        "task_id": manifest.task_id,
        "allowed_paths": list(manifest.allowed_paths),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    if len(encoded.encode("utf-8")) > _MAX_BYTES:
        raise KimiScopeManifestError("scope manifest exceeds its size limit")

    with _locked_worktree(Path(worktree)) as root_descriptor:
        _validate_scope_locations(root_descriptor, manifest.allowed_paths)
        try:
            _read_unlocked(root_descriptor)
        except KimiScopeManifestError as exc:
            if str(exc) != "scope manifest is missing":
                raise
        temporary_name = (
            f".{_MANIFEST_NAME.lstrip('.')}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
        )
        temporary_descriptor: int | None = None
        try:
            temporary_descriptor = os.open(
                temporary_name,
                os.O_CREAT
                | os.O_EXCL
                | os.O_WRONLY
                | getattr(os, "O_NOFOLLOW", 0),
                0o600,
                dir_fd=root_descriptor,
            )
            with os.fdopen(temporary_descriptor, "w", encoding="utf-8") as handle:
                temporary_descriptor = None
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(
                temporary_name,
                _MANIFEST_NAME,
                src_dir_fd=root_descriptor,
                dst_dir_fd=root_descriptor,
            )
            os.fsync(root_descriptor)
        except OSError as exc:
            try:
                os.unlink(temporary_name, dir_fd=root_descriptor)
            except OSError:
                pass
            raise KimiScopeManifestError("scope manifest cannot be written") from exc
        finally:
            if temporary_descriptor is not None:
                os.close(temporary_descriptor)
        if _read_unlocked(root_descriptor) != manifest:
            raise KimiScopeManifestError("scope manifest verification failed")
    return manifest


def verify_kimi_scope_manifest(
    worktree: Path, task_id: str, allowed_paths: list[str] | tuple[str, ...]
) -> bool:
    expected = build_kimi_scope_manifest(task_id, allowed_paths)
    with _locked_worktree(Path(worktree)) as root_descriptor:
        return _read_unlocked(root_descriptor) == expected
