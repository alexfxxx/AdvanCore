"""Focused safety and interaction checks for TASK-078 visual groundwork."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from advancore.pages import dashboard
from advancore.ui.custom_components import (
    FUEL_STATUS_COMPONENT_CSS,
    FUEL_STATUS_COMPONENT_HTML,
)
from advancore.ui.fuel_trends import (
    FuelTrendPoint,
    build_fuel_trend_figure,
    select_fuel_window,
)


class FakeStreamlit:
    def __init__(self, *, selected_window=7, recording=None, buttons=None):
        self.selected_window = selected_window
        self.recording = recording
        self.buttons = dict(buttons or {})
        self.session_state = {}
        self.messages = []
        self.button_calls = []
        self.plotly_calls = []
        self.audio_calls = []

    def _record(self, kind, value): self.messages.append((kind, str(value)))
    def subheader(self, value): self._record("subheader", value)
    def caption(self, value): self._record("caption", value)
    def success(self, value): self._record("success", value)
    def info(self, value): self._record("info", value)
    def columns(self, count): return [self for _ in range(count)]
    def selectbox(self, _label, options, **_kwargs):
        assert self.selected_window in options
        return self.selected_window
    def audio_input(self, label, **kwargs):
        self.audio_calls.append((label, kwargs))
        return self.recording
    def button(self, label, **kwargs):
        self.button_calls.append((label, kwargs))
        return self.buttons.get(label, False)
    def plotly_chart(self, figure, **kwargs):
        self.plotly_calls.append((figure, kwargs))

    def text(self): return "\n".join(value for _, value in self.messages)


def _points(count=35):
    start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    return [
        FuelTrendPoint(start + timedelta(days=index), 100.0 + index)
        for index in range(count)
    ]


def test_custom_component_is_static_local_and_reduced_motion_aware():
    component_source = FUEL_STATUS_COMPONENT_HTML + FUEL_STATUS_COMPONENT_CSS
    lowered = component_source.lower()
    assert "fuel trend console" in lowered
    assert "prefers-reduced-motion: reduce" in lowered
    assert "<script" not in lowered
    assert "http://" not in lowered
    assert "https://" not in lowered
    assert "iframe" not in lowered
    assert "{{" not in component_source


def test_fuel_figure_uses_bounded_neon_dark_layout_with_real_points():
    selected = select_fuel_window(reversed(_points()), 7)
    assert len(selected) == 7
    assert selected[0].recorded_at < selected[-1].recorded_at

    figure = build_fuel_trend_figure(_points(), 7)
    assert len(figure.data) == 2
    assert figure.data[1].line.color == "#00F2FE"
    assert figure.data[1].fill == "tozeroy"
    assert figure.layout.paper_bgcolor == "rgba(10, 15, 29, 0.98)"
    assert "last 7 readings" in figure.layout.title.text
    assert len(figure.data[1].x) == 7


def test_empty_fuel_figure_is_explicit_and_does_not_invent_a_trace():
    figure = build_fuel_trend_figure((), None)
    assert len(figure.data) == 0
    assert figure.layout.annotations[0].text == (
        "No operational fuel readings connected yet"
    )
    assert figure.layout.xaxis.visible is False
    assert figure.layout.yaxis.visible is False
    assert "all readings" in figure.layout.title.text


@pytest.mark.parametrize("window", [0, 14, 90, "7", True])
def test_fuel_window_rejects_unapproved_values(window):
    with pytest.raises(ValueError, match="not allowed"):
        select_fuel_window(_points(), window)


def test_recording_alone_never_applies_a_fuel_filter(monkeypatch):
    fake_st = FakeStreamlit(selected_window=30, recording=object())
    monkeypatch.setattr(dashboard, "st", fake_st)
    monkeypatch.setattr(dashboard, "render_fuel_status_component", lambda: None)

    dashboard._render_fuel_visual_foundation()

    assert fake_st.session_state.get(dashboard._FUEL_WINDOW_STATE_KEY) is None
    assert "Recording alone changes nothing" in fake_st.text()
    assert len(fake_st.plotly_calls) == 1
    assert "last 7 readings" in fake_st.plotly_calls[0][0].layout.title.text


def test_voice_confirmation_applies_only_selected_allowlisted_view(monkeypatch):
    label = "Confirm selected view with recording"
    fake_st = FakeStreamlit(
        selected_window=30,
        recording=object(),
        buttons={label: True},
    )
    monkeypatch.setattr(dashboard, "st", fake_st)
    monkeypatch.setattr(dashboard, "render_fuel_status_component", lambda: None)

    dashboard._render_fuel_visual_foundation()

    assert fake_st.session_state[dashboard._FUEL_WINDOW_STATE_KEY] == 30
    assert "applied after your recorded confirmation" in fake_st.text()
    assert "last 30 readings" in fake_st.plotly_calls[0][0].layout.title.text


def test_voice_control_is_disabled_without_recording_and_manual_path_works(
    monkeypatch,
):
    manual_label = "Apply selected view without voice"
    fake_st = FakeStreamlit(
        selected_window=None,
        buttons={manual_label: True},
    )
    monkeypatch.setattr(dashboard, "st", fake_st)
    monkeypatch.setattr(dashboard, "render_fuel_status_component", lambda: None)

    dashboard._render_fuel_visual_foundation()

    voice_call = next(
        kwargs
        for label, kwargs in fake_st.button_calls
        if label == "Confirm selected view with recording"
    )
    assert voice_call["disabled"] is True
    assert fake_st.session_state[dashboard._FUEL_WINDOW_STATE_KEY] is None
    assert "applied without voice" in fake_st.text()
    assert "all readings" in fake_st.plotly_calls[0][0].layout.title.text


def test_declared_dependencies_support_audio_input_and_plotly():
    requirements = (
        Path(__file__).resolve().parents[1] / "requirements.txt"
    ).read_text(encoding="utf-8")
    assert "streamlit>=1.61,<2.0" in requirements
    assert "plotly>=6.0,<7.0" in requirements
