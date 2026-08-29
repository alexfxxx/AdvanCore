"""Read-only checks for reusable module-development foundations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from advancore.module_registry import module_catalog
from advancore.services.import_contract_registry import import_contracts
from advancore.services.module_design_service import (
    MAX_MODULE_BRIEF_BYTES,
    module_brief_template_is_valid,
    read_bounded_repository_text,
)


@dataclass(frozen=True)
class ModuleReadinessItem:
    key: str
    ready: bool
    message: str


@dataclass(frozen=True)
class ModuleFoundationReadiness:
    ready: bool
    items: tuple[ModuleReadinessItem, ...]


def check_module_foundation(repository_root: Path) -> ModuleFoundationReadiness:
    """Check code-owned foundations without database, network or file writes."""
    root = Path(repository_root)
    items: list[ModuleReadinessItem] = []
    try:
        catalog = module_catalog()
        catalog_ready = bool(catalog) and len({item.module_id for item in catalog}) == len(
            catalog
        )
    except Exception:
        catalog_ready = False
    items.append(
        ModuleReadinessItem(
            "module_catalog",
            catalog_ready,
            "Module catalog is valid." if catalog_ready else "Module catalog is unavailable.",
        )
    )

    try:
        template = read_bounded_repository_text(
            root,
            "tasks/MODULE_BRIEF_TEMPLATE.md",
            max_bytes=MAX_MODULE_BRIEF_BYTES,
        )
        template_ready = bool(template) and module_brief_template_is_valid(template)
    except (OSError, UnicodeError, TypeError, ValueError):
        template_ready = False
    items.append(
        ModuleReadinessItem(
            "module_brief",
            template_ready,
            "Module brief gate is available."
            if template_ready
            else "Module brief gate is unavailable.",
        )
    )

    try:
        contracts = import_contracts()
        imports_ready = bool(contracts) and all(
            contract.preview_only_until_approved for contract in contracts
        )
    except Exception:
        imports_ready = False
    items.append(
        ModuleReadinessItem(
            "import_contracts",
            imports_ready,
            "Preview-first import contracts are valid."
            if imports_ready
            else "Import contracts are unavailable.",
        )
    )
    return ModuleFoundationReadiness(
        ready=all(item.ready for item in items), items=tuple(items)
    )
