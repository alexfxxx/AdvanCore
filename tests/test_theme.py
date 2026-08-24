"""Safety and responsiveness checks for the local command-center theme."""

from advancore.ui.theme import COMMAND_CENTER_CSS, apply_command_center_theme


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
    assert "<script" not in lowered
    assert "http://" not in lowered
    assert "https://" not in lowered
    assert "sortable" not in lowered


def test_theme_applies_static_css_as_html():
    fake_st = FakeStreamlit()
    apply_command_center_theme(fake_st)
    assert fake_st.calls == [(COMMAND_CENTER_CSS, {"unsafe_allow_html": True})]
