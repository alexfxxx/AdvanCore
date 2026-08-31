"""Immutable catalog for approved AdvanCore presentation modules."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from types import MappingProxyType
from typing import Mapping


_MODULE_ID = re.compile(r"^[a-z][a-z0-9_]{1,39}$")
_ANCHOR = re.compile(r"^[a-z][a-z0-9-]{1,63}$")


class ModuleRegistryError(ValueError):
    """Raised when code-owned module metadata is invalid or ambiguous."""


class ModuleArea(str, Enum):
    CORE = "core"
    OPERATIONS = "operations"
    GOVERNANCE = "governance"


class ModuleMaturity(str, Enum):
    FOUNDATION = "foundation"
    REGISTER = "register"
    TRANSITIONAL = "transitional"


@dataclass(frozen=True)
class ModuleDescriptor:
    module_id: str
    label: str
    area: ModuleArea
    maturity: ModuleMaturity
    streamlit_page: str | None = None
    frontend_anchor: str | None = None
    api_prefixes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not _MODULE_ID.fullmatch(self.module_id):
            raise ModuleRegistryError("Module identifier is invalid")
        if not isinstance(self.label, str) or not self.label.strip() or len(self.label) > 60:
            raise ModuleRegistryError("Module label is invalid")
        if not isinstance(self.area, ModuleArea) or not isinstance(
            self.maturity, ModuleMaturity
        ):
            raise ModuleRegistryError("Module classification is invalid")
        if self.streamlit_page is not None and (
            not isinstance(self.streamlit_page, str)
            or not self.streamlit_page.strip()
            or len(self.streamlit_page) > 60
        ):
            raise ModuleRegistryError("Streamlit page label is invalid")
        if self.frontend_anchor is not None and not _ANCHOR.fullmatch(
            self.frontend_anchor
        ):
            raise ModuleRegistryError("Frontend anchor is invalid")
        if (
            not isinstance(self.api_prefixes, tuple)
            or len(set(self.api_prefixes)) != len(self.api_prefixes)
            or any(
                not isinstance(prefix, str)
                or not prefix.startswith("/api/")
                or len(prefix) > 80
                for prefix in self.api_prefixes
            )
        ):
            raise ModuleRegistryError("Module API prefixes are invalid")


_CATALOG: tuple[ModuleDescriptor, ...] = (
    ModuleDescriptor(
        "dashboard", "Dashboard", ModuleArea.CORE, ModuleMaturity.FOUNDATION,
        streamlit_page="Dashboard", frontend_anchor="workspace",
    ),
    ModuleDescriptor(
        "knowledge_hub", "Knowledge Hub", ModuleArea.CORE,
        ModuleMaturity.REGISTER, streamlit_page="Knowledge Hub",
        frontend_anchor="knowledge-console",
        api_prefixes=("/api/knowledge",),
    ),
    ModuleDescriptor(
        "projects", "Projects", ModuleArea.CORE, ModuleMaturity.REGISTER,
        streamlit_page="Projects", frontend_anchor="projects-console",
        api_prefixes=("/api/projects",),
    ),
    ModuleDescriptor(
        "transport_operations", "Transport Operations", ModuleArea.OPERATIONS,
        ModuleMaturity.TRANSITIONAL, streamlit_page="Transport Operations",
        frontend_anchor="fleet-console",
        api_prefixes=(
            "/api/fleet", "/api/drivers", "/api/customers", "/api/routes",
            "/api/dispatch", "/api/fuel",
        ),
    ),
    ModuleDescriptor(
        "ai_center", "AI Center", ModuleArea.GOVERNANCE,
        ModuleMaturity.FOUNDATION, streamlit_page="AI Center",
        frontend_anchor="controller-console",
        api_prefixes=("/api/orchestrations",),
    ),
    ModuleDescriptor(
        "activity_log", "Activity Log", ModuleArea.GOVERNANCE,
        ModuleMaturity.REGISTER, streamlit_page="Activity Log",
    ),
    ModuleDescriptor(
        "settings", "Settings", ModuleArea.CORE, ModuleMaturity.FOUNDATION,
        streamlit_page="Settings", frontend_anchor="preferences-console",
    ),
)


def _build_index(catalog: tuple[ModuleDescriptor, ...]) -> Mapping[str, ModuleDescriptor]:
    identifiers = [item.module_id for item in catalog]
    labels = [item.label.strip().casefold() for item in catalog]
    page_labels = [
        item.streamlit_page.strip().casefold()
        for item in catalog
        if item.streamlit_page
    ]
    if (
        len(set(identifiers)) != len(identifiers)
        or len(set(labels)) != len(labels)
        or len(set(page_labels)) != len(page_labels)
    ):
        raise ModuleRegistryError("Module catalog contains duplicate identities")
    return MappingProxyType({item.module_id: item for item in catalog})


_BY_ID = _build_index(_CATALOG)


def module_catalog() -> tuple[ModuleDescriptor, ...]:
    return _CATALOG


def get_module(module_id: str) -> ModuleDescriptor:
    if not isinstance(module_id, str) or module_id not in _BY_ID:
        raise ModuleRegistryError("Unknown module identifier")
    return _BY_ID[module_id]


def streamlit_navigation() -> tuple[tuple[str, str], ...]:
    return tuple(
        (item.module_id, item.streamlit_page)
        for item in _CATALOG
        if item.streamlit_page is not None
    )
