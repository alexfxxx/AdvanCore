"""Typed Plotly fuel-trend visuals with an honest no-data state."""

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from math import isfinite
from typing import Iterable

import plotly.graph_objects as go


ALLOWED_FUEL_WINDOWS = (7, 30, None)


@dataclass(frozen=True)
class FuelTrendPoint:
    """One future operational fuel reading supplied by a governed data service."""

    recorded_at: datetime
    litres: float

    @classmethod
    def from_recorded_date(cls, recorded_on: date, litres: float) -> "FuelTrendPoint":
        if type(recorded_on) is not date:
            raise TypeError("Recorded fuel date must be a date value.")
        return cls(datetime.combine(recorded_on, time.min, tzinfo=timezone.utc), litres)


def _validated_points(points: Iterable[FuelTrendPoint]) -> tuple[FuelTrendPoint, ...]:
    validated = []
    for point in points:
        if not isinstance(point, FuelTrendPoint):
            raise TypeError("Fuel trend points must use FuelTrendPoint.")
        if not isinstance(point.recorded_at, datetime):
            raise TypeError("Fuel trend timestamps must be datetime values.")
        if not isinstance(point.litres, (int, float)) or isinstance(point.litres, bool):
            raise TypeError("Fuel trend values must be numeric.")
        if not isfinite(float(point.litres)) or point.litres < 0:
            raise ValueError("Fuel trend values must be finite and non-negative.")
        validated.append(point)
    return tuple(sorted(validated, key=lambda item: item.recorded_at))


def select_fuel_window(
    points: Iterable[FuelTrendPoint], window: int | None
) -> tuple[FuelTrendPoint, ...]:
    """Return the newest allowlisted number of readings in chronological order."""
    if window not in ALLOWED_FUEL_WINDOWS:
        raise ValueError("Fuel trend window is not allowed.")
    validated = _validated_points(points)
    return validated if window is None else validated[-window:]


def build_fuel_trend_figure(
    points: Iterable[FuelTrendPoint], window: int | None = 7
) -> go.Figure:
    """Build a dark neon line chart without inventing missing observations."""
    selected = select_fuel_window(points, window)
    figure = go.Figure()

    if selected:
        x_values = [point.recorded_at for point in selected]
        y_values = [float(point.litres) for point in selected]
        figure.add_trace(
            go.Scatter(
                x=x_values,
                y=y_values,
                mode="lines",
                line={"color": "rgba(0, 242, 254, 0.18)", "width": 11},
                hoverinfo="skip",
                showlegend=False,
            )
        )
        figure.add_trace(
            go.Scatter(
                x=x_values,
                y=y_values,
                mode="lines+markers",
                line={"color": "#00F2FE", "width": 3, "shape": "spline"},
                marker={
                    "color": "#A5F3FC",
                    "line": {"color": "#6366F1", "width": 1.5},
                    "size": 7,
                },
                fill="tozeroy",
                fillcolor="rgba(0, 242, 254, 0.075)",
                name="Fuel used",
                hovertemplate="%{x|%d %b %Y}<br>%{y:.2f} L<extra></extra>",
            )
        )
    else:
        figure.add_annotation(
            text="No operational fuel readings recorded yet",
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
            showarrow=False,
            font={"color": "#A5B4FC", "size": 15},
        )

    window_label = "all recorded days" if window is None else f"last {window} recorded days"
    figure.update_layout(
        title={
            "text": f"Fuel usage trend · {window_label}",
            "font": {"color": "#F8FAFC", "size": 17},
            "x": 0.03,
        },
        height=360,
        margin={"l": 54, "r": 24, "t": 66, "b": 48},
        paper_bgcolor="rgba(10, 15, 29, 0.98)",
        plot_bgcolor="rgba(15, 23, 42, 0.76)",
        font={"color": "#CBD5E1"},
        hovermode="x unified",
        showlegend=False,
        xaxis={
            "visible": bool(selected),
            "gridcolor": "rgba(99, 102, 241, 0.14)",
            "linecolor": "rgba(99, 102, 241, 0.38)",
            "zeroline": False,
            "title": None,
        },
        yaxis={
            "visible": bool(selected),
            "gridcolor": "rgba(0, 242, 254, 0.10)",
            "linecolor": "rgba(99, 102, 241, 0.38)",
            "rangemode": "tozero",
            "title": {"text": "Litres", "font": {"color": "#94A3B8"}},
            "zerolinecolor": "rgba(148, 163, 184, 0.18)",
        },
    )
    return figure
