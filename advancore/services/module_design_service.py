"""Read-only completeness gate for owner-approved business module briefs."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import stat


MAX_MODULE_BRIEF_BYTES = 128 * 1024
REQUIRED_MODULE_BRIEF_SECTIONS = (
    "Module identity",
    "Business problem",
    "Facts",
    "Required fields",
    "Reference sources",
    "Calculations",
    "Workflows and approvals",
    "Imports",
    "Reports and filters",
    "Database impact",
    "Security and compliance",
    "Owner decisions",
    "Acceptance examples",
)
_PLACEHOLDER = re.compile(
    r"\b(?:TBD|TODO|PLACEHOLDER|DESCRIBE HERE|OWNER TO CONFIRM)\b|<[^>]+>",
    re.IGNORECASE,
)
_STATUS = re.compile(r"^STATUS:\s*([A-Z_]+)\s*$", re.IGNORECASE)
_MODULE_ID = re.compile(r"^[a-z][a-z0-9_]{1,39}$")
_MODULE_ID_LINE = re.compile(r"^MODULE_ID:\s*([a-z][a-z0-9_]{1,39})\s*$")
_TASK_ID = re.compile(r"^TASK-(\d+)$")
_GATE_CLASSIFICATION = re.compile(
    r"^Classification:\s*(BUSINESS_MODULE|NON_MODULE)\s*$", re.IGNORECASE
)
_GATE_BRIEF = re.compile(r"^Approved brief:\s*(.+?)\s*$", re.IGNORECASE)
_GATE_MODULE_ID = re.compile(r"^Module identifier:\s*(.+?)\s*$", re.IGNORECASE)
MODULE_GATE_REQUIRED_FROM_TASK = 164


@dataclass(frozen=True)
class ModuleBriefReadiness:
    ready: bool
    module_id: str | None
    status_approved: bool
    fact_count: int
    missing_sections: tuple[str, ...]
    placeholder_sections: tuple[str, ...]
    insubstantial_sections: tuple[str, ...]
    duplicate_sections: tuple[str, ...]
    owner_decision_required: bool


@dataclass(frozen=True)
class GovernedTaskModuleGate:
    ready: bool
    classification: str | None
    message: str


def _sections(text: str) -> tuple[dict[str, str], tuple[str, ...]]:
    collected: dict[str, list[str]] = {}
    duplicates: list[str] = []
    active: str | None = None
    for line in text.splitlines():
        if line.startswith("## "):
            active = line[3:].strip()
            if active in collected:
                duplicates.append(active)
                active = None
            else:
                collected[active] = []
        elif active is not None:
            collected[active].append(line)
    return (
        {name: "\n".join(lines).strip() for name, lines in collected.items()},
        tuple(dict.fromkeys(duplicates)),
    )


def _canonical_status_is_approved(text: str) -> bool:
    lines = text.splitlines()
    first_section = next(
        (index for index, line in enumerate(lines) if line.startswith("## ")),
        len(lines),
    )
    matches = [
        (index, match.group(1).upper())
        for index, line in enumerate(lines)
        if (match := _STATUS.fullmatch(line.strip())) is not None
    ]
    return len(matches) == 1 and matches[0][0] < first_section and matches[0][1] == "APPROVED"


def _canonical_module_id(text: str) -> str | None:
    lines = text.splitlines()
    first_section = next(
        (index for index, line in enumerate(lines) if line.startswith("## ")),
        len(lines),
    )
    matches = [
        (index, match.group(1))
        for index, line in enumerate(lines)
        if (match := _MODULE_ID_LINE.fullmatch(line.strip())) is not None
    ]
    if len(matches) != 1 or matches[0][0] >= first_section:
        return None
    return matches[0][1]


def module_brief_template_is_valid(text: str) -> bool:
    """Validate the exact top-level template markers and required sections."""
    if not isinstance(text, str) or not text or "\x00" in text:
        return False
    lines = text.splitlines()
    first_section = next(
        (index for index, line in enumerate(lines) if line.startswith("## ")),
        len(lines),
    )
    statuses = [
        (index, match.group(1).upper())
        for index, line in enumerate(lines)
        if (match := _STATUS.fullmatch(line.strip())) is not None
    ]
    module_markers = [
        index
        for index, line in enumerate(lines)
        if line == "MODULE_ID: TODO"
    ]
    any_module_markers = [
        index for index, line in enumerate(lines) if line.strip().startswith("MODULE_ID:")
    ]
    sections, duplicates = _sections(text)
    return (
        len(statuses) == 1
        and lines[statuses[0][0]] == "STATUS: DRAFT"
        and statuses[0][0] < first_section
        and len(module_markers) == 1
        and module_markers[0] < first_section
        and any_module_markers == module_markers
        and not duplicates
        and all(sections.get(section) for section in REQUIRED_MODULE_BRIEF_SECTIONS)
    )


def _substantive_fact_lines(section: str) -> tuple[str, ...]:
    facts: list[str] = []
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- FACT:"):
            continue
        statement = stripped.removeprefix("- FACT:").strip()
        if len(statement) >= 8 and _PLACEHOLDER.search(statement) is None:
            facts.append(statement)
    return tuple(facts)


def _section_is_substantive(name: str, content: str) -> bool:
    if name == "Facts":
        return bool(_substantive_fact_lines(content))
    if name == "Owner decisions":
        return content.strip().casefold() == "none"
    if name in {"Calculations", "Imports", "Database impact"} and content.strip().casefold() == "none":
        return True
    plain = re.sub(r"[^A-Za-z0-9]+", "", content)
    return len(plain) >= 12


def evaluate_module_brief(text: str) -> ModuleBriefReadiness:
    """Return bounded readiness evidence without writing or interpreting policy."""
    if not isinstance(text, str):
        raise TypeError("Module brief must be text")
    try:
        size = len(text.encode("utf-8"))
    except UnicodeError as exc:
        raise ValueError("Module brief is not valid UTF-8 text") from exc
    if size == 0 or size > MAX_MODULE_BRIEF_BYTES or "\x00" in text:
        raise ValueError("Module brief size or content is invalid")

    sections, duplicates = _sections(text)
    missing = tuple(
        name for name in REQUIRED_MODULE_BRIEF_SECTIONS if not sections.get(name)
    )
    placeholders = tuple(
        name
        for name in REQUIRED_MODULE_BRIEF_SECTIONS
        if name in sections and _PLACEHOLDER.search(sections[name])
    )
    facts = _substantive_fact_lines(sections.get("Facts", ""))
    insubstantial = tuple(
        name
        for name in REQUIRED_MODULE_BRIEF_SECTIONS
        if name in sections
        and name not in missing
        and not _section_is_substantive(name, sections[name])
    )
    owner_text = sections.get("Owner decisions", "").strip()
    owner_decision_required = bool(owner_text and owner_text.casefold() != "none")
    status_approved = _canonical_status_is_approved(text)
    module_id = _canonical_module_id(text)
    ready = (
        status_approved
        and module_id is not None
        and not missing
        and not placeholders
        and not insubstantial
        and not duplicates
        and bool(facts)
        and not owner_decision_required
    )
    return ModuleBriefReadiness(
        ready=ready,
        module_id=module_id,
        status_approved=status_approved,
        fact_count=len(facts),
        missing_sections=missing,
        placeholder_sections=placeholders,
        insubstantial_sections=insubstantial,
        duplicate_sections=duplicates,
        owner_decision_required=owner_decision_required,
    )


def _safe_brief_parts(raw_path: str) -> tuple[str, ...] | None:
    if not raw_path or raw_path.startswith(("/", "\\", "~")):
        return None
    parts = raw_path.replace("\\", "/").split("/")
    if (
        len(parts) < 3
        or parts[:2] != ["tasks", "module-briefs"]
        or any(part in {"", ".", ".."} for part in parts)
        or not parts[-1].endswith(".md")
    ):
        return None
    return tuple(parts)


def normalize_module_brief_reference(raw_path: str) -> str:
    """Return the one canonical approved-brief path accepted by the gate."""
    if not isinstance(raw_path, str):
        raise ValueError("Approved module brief reference must be text")
    parts = _safe_brief_parts(raw_path)
    if parts is None:
        raise ValueError("Approved module brief reference is invalid")
    return "/".join(parts)


def read_bounded_repository_text(
    repository_root: Path,
    repository_path: str,
    *,
    max_bytes: int = MAX_MODULE_BRIEF_BYTES,
) -> str | None:
    """Read a regular repository file through a bounded no-symlink traversal."""
    if (
        not isinstance(repository_path, str)
        or not repository_path
        or repository_path.startswith(("/", "\\", "~"))
        or not isinstance(max_bytes, int)
        or not 0 < max_bytes <= MAX_MODULE_BRIEF_BYTES
    ):
        return None
    parts = tuple(repository_path.replace("\\", "/").split("/"))
    if not parts or any(part in {"", ".", ".."} for part in parts):
        return None
    opened: list[int] = []
    try:
        absolute_root = Path(os.path.abspath(os.fspath(repository_root)))
        current_fd = os.open(
            os.path.sep, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        )
        opened.append(current_fd)
        for part in absolute_root.parts[1:]:
            expected = os.stat(part, dir_fd=current_fd, follow_symlinks=False)
            if not stat.S_ISDIR(expected.st_mode):
                return None
            next_fd = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=current_fd,
            )
            actual = os.fstat(next_fd)
            if (actual.st_dev, actual.st_ino) != (expected.st_dev, expected.st_ino):
                os.close(next_fd)
                return None
            current_fd = next_fd
            opened.append(current_fd)
        for index, part in enumerate(parts):
            is_leaf = index == len(parts) - 1
            expected = os.stat(part, dir_fd=current_fd, follow_symlinks=False)
            if is_leaf:
                if not stat.S_ISREG(expected.st_mode):
                    return None
                flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
            else:
                if not stat.S_ISDIR(expected.st_mode):
                    return None
                flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY
            next_fd = os.open(part, flags, dir_fd=current_fd)
            actual = os.fstat(next_fd)
            if (actual.st_dev, actual.st_ino) != (expected.st_dev, expected.st_ino):
                os.close(next_fd)
                return None
            current_fd = next_fd
            opened.append(current_fd)
        metadata = os.fstat(current_fd)
        if not stat.S_ISREG(metadata.st_mode):
            return None
        chunks: list[bytes] = []
        remaining = max_bytes + 1
        while remaining:
            chunk = os.read(current_fd, min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        if len(data) > max_bytes:
            return None
        return data.decode("utf-8")
    except (OSError, UnicodeError, ValueError):
        return None
    finally:
        for descriptor in reversed(opened):
            try:
                os.close(descriptor)
            except OSError:
                pass


def _read_approved_brief(repository_root: Path, raw_path: str) -> str | None:
    """Read one canonical approved brief through the repository boundary."""
    try:
        canonical = normalize_module_brief_reference(raw_path)
    except ValueError:
        return None
    return read_bounded_repository_text(
        repository_root,
        canonical,
        max_bytes=MAX_MODULE_BRIEF_BYTES,
    )


def evaluate_governed_task_module_gate(
    task_text: str,
    *,
    task_id: str,
    repository_root: Path,
) -> GovernedTaskModuleGate:
    """Enforce a declared module classification on all post-programme tasks."""
    match = _TASK_ID.fullmatch(task_id)
    if match is None:
        return GovernedTaskModuleGate(False, None, "Task identifier is invalid.")
    if int(match.group(1)) < MODULE_GATE_REQUIRED_FROM_TASK:
        return GovernedTaskModuleGate(True, None, "Legacy task predates the module gate.")

    sections, duplicates = _sections(task_text)
    gate = sections.get("Module design gate")
    if gate is None or "Module design gate" in duplicates:
        return GovernedTaskModuleGate(False, None, "Module design gate is missing or duplicated.")

    gate_lines = [line.strip() for line in gate.splitlines() if line.strip()]
    classification_matches = [
        match.group(1).upper()
        for line in gate_lines
        if (match := _GATE_CLASSIFICATION.fullmatch(line)) is not None
    ]
    brief_matches = [
        match.group(1).strip()
        for line in gate_lines
        if (match := _GATE_BRIEF.fullmatch(line)) is not None
    ]
    module_id_matches = [
        match.group(1).strip()
        for line in gate_lines
        if (match := _GATE_MODULE_ID.fullmatch(line)) is not None
    ]
    if (
        len(gate_lines) != 3
        or len(classification_matches) != 1
        or len(brief_matches) != 1
        or len(module_id_matches) != 1
    ):
        return GovernedTaskModuleGate(False, None, "Module design gate fields are ambiguous.")

    classification = classification_matches[0]
    raw_brief = brief_matches[0]
    task_module_id = module_id_matches[0]
    if classification == "NON_MODULE":
        if raw_brief.casefold() != "none" or task_module_id.casefold() != "none":
            return GovernedTaskModuleGate(False, classification, "Non-module task must declare no module or brief.")
        return GovernedTaskModuleGate(True, classification, "Non-module classification is explicit.")

    if _MODULE_ID.fullmatch(task_module_id) is None:
        return GovernedTaskModuleGate(False, classification, "Business module identifier is invalid.")
    brief_text = _read_approved_brief(Path(repository_root), raw_brief)
    if brief_text is None:
        return GovernedTaskModuleGate(False, classification, "Approved module brief is unavailable or unsafe.")
    try:
        readiness = evaluate_module_brief(brief_text)
    except (TypeError, ValueError):
        return GovernedTaskModuleGate(False, classification, "Approved module brief cannot be validated.")
    if not readiness.ready:
        return GovernedTaskModuleGate(False, classification, "Module brief is not implementation-ready.")
    if readiness.module_id != task_module_id:
        return GovernedTaskModuleGate(False, classification, "Task and module brief identities do not match.")
    return GovernedTaskModuleGate(True, classification, "Approved module brief passed validation.")
