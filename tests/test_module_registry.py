import pytest

import advancore.module_registry as registry
from advancore.module_registry import (
    ModuleArea,
    ModuleDescriptor,
    ModuleMaturity,
    ModuleRegistryError,
    get_module,
    module_catalog,
    streamlit_navigation,
)


def test_catalog_is_unique_deterministic_and_contains_existing_pages():
    catalog = module_catalog()
    assert tuple(item.module_id for item in catalog) == (
        "dashboard",
        "knowledge_hub",
        "projects",
        "transport_operations",
        "ai_center",
        "activity_log",
        "settings",
    )
    assert len({item.module_id for item in catalog}) == len(catalog)
    assert dict(streamlit_navigation())["transport_operations"] == "Transport Operations"
    assert get_module("dashboard").frontend_anchor == "workspace"
    assert get_module("projects").frontend_anchor == "projects-console"
    assert get_module("knowledge_hub").frontend_anchor == "knowledge-console"


def test_catalog_is_immutable_and_unknown_module_fails_closed():
    assert isinstance(module_catalog(), tuple)
    with pytest.raises(ModuleRegistryError, match="Unknown"):
        get_module("finance")


def test_duplicate_public_module_labels_fail_closed():
    first = ModuleDescriptor(
        "first_module", "Shared label", ModuleArea.CORE, ModuleMaturity.FOUNDATION
    )
    second = ModuleDescriptor(
        "second_module", "shared LABEL", ModuleArea.CORE, ModuleMaturity.FOUNDATION
    )
    with pytest.raises(ModuleRegistryError, match="duplicate"):
        registry._build_index((first, second))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"module_id": "Bad ID"},
        {"label": ""},
        {"frontend_anchor": "../unsafe"},
        {"api_prefixes": ("/api/x", "/api/x")},
        {"api_prefixes": ("https://example.test",)},
    ],
)
def test_malformed_descriptor_fails_closed(kwargs):
    values = {
        "module_id": "sample_module",
        "label": "Sample",
        "area": ModuleArea.CORE,
        "maturity": ModuleMaturity.FOUNDATION,
        "frontend_anchor": "sample-module",
        "api_prefixes": ("/api/sample",),
    }
    values.update(kwargs)
    with pytest.raises(ModuleRegistryError):
        ModuleDescriptor(**values)


def test_app_navigation_is_registry_driven():
    source = open("app.py", encoding="utf-8").read()
    assert "streamlit_navigation()" in source
    assert '_PAGE_RENDERERS[_PAGE_BY_LABEL[page]]()' in source
