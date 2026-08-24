"""Safety and responsiveness checks for the local command-center theme."""

from advancore.ui.theme import (
    COMMAND_CENTER_CSS,
    _ICON_DIRECTORY,
    _NAVIGATION_ICONS,
    _svg_data_uri,
    apply_command_center_theme,
)


class FakeStreamlit:
    def __init__(self):
        self.calls = []

    def markdown(self, value, **kwargs):
        self.calls.append((value, kwargs))


def test_theme_is_local_responsive_and_has_no_script_dependency():
    lowered = COMMAND_CENTER_CSS.lower()
    assert "@media (max-width: 640px)" in COMMAND_CENTER_CSS
    assert "@media (max-width: 900px)" in COMMAND_CENTER_CSS
    assert "flex-wrap: wrap" in COMMAND_CENTER_CSS
    assert 'data-testid="stMetric"' in COMMAND_CENTER_CSS
    assert 'data-testid="stMetricValue"' in COMMAND_CENTER_CSS
    assert "white-space: normal !important" in COMMAND_CENTER_CSS
    assert "overflow: visible !important" in COMMAND_CENTER_CSS
    assert "text-overflow: clip !important" in COMMAND_CENTER_CSS
    assert "overflow-wrap: anywhere" in COMMAND_CENTER_CSS
    assert '[data-testid="stMetricValue"] > div > p' in COMMAND_CENTER_CSS
    assert '[data-testid="stSidebar"] * { color: #26364d !important; }' in (
        COMMAND_CENTER_CSS
    )
    assert "label > div > div > div:first-child" in COMMAND_CENTER_CSS
    assert "background: #ffffff" in COMMAND_CENTER_CSS
    assert "data:image/svg+xml" in COMMAND_CENTER_CSS
    assert COMMAND_CENTER_CSS.count("data:image/svg+xml") == 6
    assert "@keyframes adv-enter" in COMMAND_CENTER_CSS
    assert "prefers-reduced-motion: reduce" in COMMAND_CENTER_CSS
    assert "<script" not in lowered
    assert "http://" not in lowered
    assert "https://" not in lowered
    assert "sortable" not in lowered


def test_navigation_icons_are_local_validated_svg_repo_assets():
    sources = (_ICON_DIRECTORY / "README.md").read_text(encoding="utf-8")
    assert "CC0" in sources
    for icon in _NAVIGATION_ICONS:
        svg = (_ICON_DIRECTORY / f"{icon}.svg").read_text(encoding="utf-8")
        lowered = svg.lower()
        assert "<svg" in lowered and "</svg>" in lowered
        assert "<script" not in lowered
        assert "<foreignobject" not in lowered
        assert _svg_data_uri(icon).startswith("data:image/svg+xml,")


def test_theme_applies_static_css_as_html():
    fake_st = FakeStreamlit()
    apply_command_center_theme(fake_st)
    assert fake_st.calls == [(COMMAND_CENTER_CSS, {"unsafe_allow_html": True})]
