"""Local, light, dependency-free command-center theme."""

from pathlib import Path
import re
from urllib.parse import quote


_ICON_DIRECTORY = Path(__file__).resolve().parents[1] / "assets" / "icons"
_NAVIGATION_ICONS = (
    "dashboard",
    "knowledge",
    "projects",
    "ai",
    "activity",
    "settings",
)


def _svg_data_uri(name: str) -> str:
    """Return one validated local SVG as a CSS data URI."""
    path = _ICON_DIRECTORY / f"{name}.svg"
    svg = path.read_text(encoding="utf-8")
    if (
        path.is_symlink()
        or len(svg) > 20_000
        or not re.search(r"<svg\b[\s\S]*</svg>\s*$", svg, re.IGNORECASE)
        or re.search(
            r"<script|<foreignObject|on[a-z]+\s*=|"
            r"(?:href|src)\s*=\s*[\"'](?:https?:|//|data:)",
            svg,
            re.IGNORECASE,
        )
    ):
        raise ValueError("Navigation icon is unsafe or invalid.")
    svg = re.sub(r"<\?xml[\s\S]*?\?>", "", svg).strip()
    svg = re.sub(r"<!--[\s\S]*?-->", "", svg).strip()
    return f"data:image/svg+xml,{quote(svg, safe='')}"


def _navigation_icon_css() -> str:
    rules = []
    for position, icon in enumerate(_NAVIGATION_ICONS, start=1):
        rules.append(
            "[data-testid=\"stSidebar\"] [role=\"radiogroup\"] "
            f"label:nth-child({position}) p::before {{"
            "content: \"\"; display: inline-block; width: 20px; height: 20px; "
            "margin-right: 11px; flex: 0 0 20px; vertical-align: -4px; "
            f"background: url(\"{_svg_data_uri(icon)}\") center / contain no-repeat;"
            "}"
        )
    return "\n".join(rules)


COMMAND_CENTER_CSS = f"""
<style>
:root {{
    --adv-bg: #f5f7fb;
    --adv-surface: #ffffff;
    --adv-surface-soft: #eef3f9;
    --adv-border: #d9e2ef;
    --adv-text: #142033;
    --adv-muted: #59677a;
    --adv-accent: #2156d9;
    --adv-accent-soft: #edf3ff;
}}
[data-testid="stAppViewContainer"] {{
    background:
        radial-gradient(circle at 88% 3%, rgba(86, 127, 235, 0.10), transparent 25%),
        linear-gradient(180deg, #fbfcfe 0%, var(--adv-bg) 100%);
    color: var(--adv-text);
}}
[data-testid="stHeader"] {{
    background: rgba(251, 252, 254, 0.88);
    border-bottom: 1px solid rgba(217, 226, 239, 0.72);
    backdrop-filter: blur(12px);
}}
[data-testid="stSidebar"] {{
    background: #ffffff;
    border-right: 1px solid var(--adv-border);
}}
[data-testid="stSidebar"] * {{ color: #26364d !important; }}
[data-testid="stSidebar"] [role="radiogroup"] label {{
    margin: 4px 8px;
    padding: 11px 12px;
    border: 1px solid transparent;
    border-radius: 12px;
    transition: background-color 160ms ease, border-color 160ms ease,
        transform 160ms ease, box-shadow 160ms ease;
}}
[data-testid="stSidebar"] [role="radiogroup"]
label > div > div > div:first-child {{
    display: none;
}}
[data-testid="stSidebar"] [role="radiogroup"] label:hover {{
    background: #f5f8fd;
    border-color: #e2e9f3;
    transform: translateX(2px);
}}
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {{
    background: var(--adv-accent-soft);
    border-color: #c9d8fb;
    box-shadow: 0 8px 22px rgba(33, 86, 217, 0.10);
}}
[data-testid="stSidebar"] [role="radiogroup"] label p {{
    display: flex;
    align-items: center;
    color: #26364d !important;
    font-size: 0.94rem !important;
    font-weight: 650 !important;
}}
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) p {{
    color: #1648c2 !important;
}}
{_navigation_icon_css()}
[data-testid="stMetric"] {{
    background: linear-gradient(145deg, #ffffff, #fbfcff);
    border: 1px solid var(--adv-border);
    border-radius: 16px;
    padding: 16px 18px;
    min-height: 112px;
    box-shadow: 0 10px 28px rgba(40, 60, 92, 0.07);
    transition: transform 180ms ease, box-shadow 180ms ease,
        border-color 180ms ease;
}}
[data-testid="stMetric"]:hover {{
    transform: translateY(-3px);
    border-color: #b9c9e4;
    box-shadow: 0 16px 36px rgba(40, 73, 132, 0.12);
}}
[data-testid="stMetricLabel"] {{ color: var(--adv-muted); }}
[data-testid="stMetricValue"],
[data-testid="stMetricValue"] > div,
[data-testid="stMetricValue"] > div > p {{
    color: var(--adv-text);
    white-space: normal !important;
    overflow: visible !important;
    text-overflow: clip !important;
    overflow-wrap: anywhere;
    line-height: 1.18;
}}
div[data-testid="stExpander"] {{
    background: rgba(255, 255, 255, 0.90);
    border: 1px solid var(--adv-border);
    border-radius: 16px;
    box-shadow: 0 8px 24px rgba(40, 60, 92, 0.05);
    transition: border-color 180ms ease, box-shadow 180ms ease;
}}
div[data-testid="stExpander"]:hover {{
    border-color: #bdcbe0;
    box-shadow: 0 12px 30px rgba(40, 73, 132, 0.09);
}}
.stButton > button {{
    border-radius: 11px;
    border: 1px solid #2b5ee0;
    background: linear-gradient(135deg, #2e63e8, #1748c4);
    color: white;
    box-shadow: 0 7px 18px rgba(33, 86, 217, 0.18);
    transition: transform 160ms ease, box-shadow 160ms ease,
        border-color 160ms ease;
}}
.stButton > button p,
.stButton > button span {{
    color: #ffffff !important;
}}
.stButton > button:disabled p,
.stButton > button:disabled span {{
    color: rgba(255, 255, 255, 0.76) !important;
}}
.stButton > button:hover {{
    border-color: #153da6;
    color: white;
    transform: translateY(-2px);
    box-shadow: 0 11px 28px rgba(33, 86, 217, 0.28),
        0 0 0 3px rgba(75, 119, 238, 0.10);
}}
.stButton > button:focus-visible {{
    outline: 3px solid rgba(33, 86, 217, 0.24);
    outline-offset: 3px;
}}
[data-baseweb="input"], [data-baseweb="textarea"],
[data-baseweb="select"] > div {{
    background: #ffffff;
    border-color: #cad6e6;
    transition: border-color 160ms ease, box-shadow 160ms ease,
        transform 160ms ease;
}}
[data-baseweb="input"]:focus-within,
[data-baseweb="textarea"]:focus-within,
[data-baseweb="select"] > div:focus-within {{
    border-color: var(--adv-accent);
    box-shadow: 0 0 0 3px rgba(33, 86, 217, 0.12);
    transform: translateY(-1px);
}}
h1, h2, h3 {{ color: var(--adv-text); letter-spacing: -0.025em; }}
h1 {{ color: #173f9e; font-weight: 850; }}
p, label {{ color: #334155; }}
.block-container > div {{ animation: adv-enter 300ms ease-out both; }}
@keyframes adv-enter {{
    from {{ opacity: 0; transform: translateY(7px); }}
    to {{ opacity: 1; transform: translateY(0); }}
}}
@media (max-width: 900px) {{
    [data-testid="stHorizontalBlock"] {{ flex-wrap: wrap; }}
    [data-testid="column"] {{ min-width: 220px; flex: 1 1 calc(50% - 1rem); }}
}}
@media (max-width: 640px) {{
    .block-container {{ padding: 1.2rem 1rem 5rem; }}
    [data-testid="column"] {{ min-width: 100%; flex: 1 1 100%; }}
    [data-testid="stMetric"] {{ min-height: 94px; padding: 12px 14px; }}
    h1 {{ font-size: 1.75rem; }}
}}
@media (prefers-reduced-motion: reduce) {{
    *, *::before, *::after {{
        animation-duration: 0.01ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: 0.01ms !important;
        scroll-behavior: auto !important;
    }}
}}
</style>
"""


def apply_command_center_theme(streamlit_module) -> None:
    """Apply static local CSS; no user content or external scripts are inserted."""
    streamlit_module.markdown(COMMAND_CENTER_CSS, unsafe_allow_html=True)
