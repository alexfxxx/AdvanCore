"""Small, local-only Streamlit components for the command center."""

import streamlit as st


FUEL_STATUS_COMPONENT_HTML = """
<section class="fuel-hud" aria-label="Fuel trend system status">
    <p class="fuel-hud__eyebrow">Local visual component</p>
    <h3 class="fuel-hud__title">Fuel trend console</h3>
    <div class="fuel-hud__state">
        <span class="fuel-hud__dot" aria-hidden="true"></span>
        Visual layer ready · operational fuel source not connected
    </div>
</section>
"""


FUEL_STATUS_COMPONENT_CSS = """
    :root { color-scheme: dark; }
    * { box-sizing: border-box; }
    .fuel-hud {
        position: relative;
        overflow: hidden;
        min-height: 92px;
        padding: 17px 19px;
        border: 1px solid rgba(99, 102, 241, 0.58);
        border-radius: 15px;
        background:
            radial-gradient(circle at 88% 12%, rgba(0, 242, 254, 0.15), transparent 34%),
            linear-gradient(135deg, rgba(10, 15, 29, 0.98), rgba(15, 23, 42, 0.91));
        box-shadow: inset 0 0 22px rgba(99, 102, 241, 0.10);
        color: #e2e8f0;
    }
    .fuel-hud::after {
        content: "";
        position: absolute;
        inset: auto 0 0;
        height: 2px;
        background: linear-gradient(90deg, transparent, #6366f1, #00f2fe, transparent);
        animation: hud-scan 3.4s ease-in-out infinite;
    }
    .fuel-hud__eyebrow {
        margin: 0 0 6px;
        color: #67e8f9;
        font: 700 11px/1.2 ui-monospace, SFMono-Regular, Menlo, monospace;
        letter-spacing: 0.16em;
        text-transform: uppercase;
    }
    .fuel-hud__title {
        margin: 0;
        color: #f8fafc;
        font-size: 18px;
        font-weight: 750;
        letter-spacing: -0.02em;
    }
    .fuel-hud__state {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        margin-top: 8px;
        color: #a5b4fc;
        font-size: 12px;
    }
    .fuel-hud__dot {
        width: 7px;
        height: 7px;
        border-radius: 999px;
        background: #00f2fe;
        box-shadow: 0 0 12px rgba(0, 242, 254, 0.82);
        animation: hud-pulse 1.8s ease-in-out infinite;
    }
    @keyframes hud-scan {
        0%, 100% { opacity: 0.38; transform: translateX(-18%); }
        50% { opacity: 1; transform: translateX(18%); }
    }
    @keyframes hud-pulse {
        0%, 100% { opacity: 0.55; transform: scale(0.86); }
        50% { opacity: 1; transform: scale(1.12); }
    }
    @media (prefers-reduced-motion: reduce) {
        .fuel-hud::after, .fuel-hud__dot { animation: none; }
    }
"""


_fuel_status_component = st.components.v2.component(
    name="advancore_fuel_status",
    html=FUEL_STATUS_COMPONENT_HTML,
    css=FUEL_STATUS_COMPONENT_CSS,
    isolate_styles=True,
)


def render_fuel_status_component() -> None:
    """Mount fixed local HTML in an isolated modern Streamlit component."""
    _fuel_status_component(key="advancore_fuel_status")
