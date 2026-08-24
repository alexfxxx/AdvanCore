"""Local, dependency-free command-center theme."""


COMMAND_CENTER_CSS = """
<style>
:root {
    --adv-bg: #080f1f;
    --adv-surface: #0f172a;
    --adv-surface-soft: #172033;
    --adv-border: #263449;
    --adv-text: #f8fafc;
    --adv-muted: #94a3b8;
    --adv-accent: #818cf8;
}
[data-testid="stAppViewContainer"],
[data-testid="stHeader"] {
    background: radial-gradient(circle at top right, #172554 0, var(--adv-bg) 38%);
    color: var(--adv-text);
}
[data-testid="stSidebar"] {
    background: #070d19;
    border-right: 1px solid var(--adv-border);
}
[data-testid="stMetric"] {
    background: linear-gradient(145deg, var(--adv-surface), #0b1324);
    border: 1px solid var(--adv-border);
    border-radius: 16px;
    padding: 16px 18px;
    min-height: 112px;
    box-shadow: 0 12px 30px rgba(2, 6, 23, 0.24);
}
[data-testid="stMetricLabel"] { color: var(--adv-muted); }
[data-testid="stMetricValue"] { color: var(--adv-text); }
div[data-testid="stExpander"] {
    background: rgba(15, 23, 42, 0.82);
    border: 1px solid var(--adv-border);
    border-radius: 16px;
}
.stButton > button {
    border-radius: 10px;
    border: 1px solid #4f46e5;
    background: #4338ca;
    color: white;
}
.stButton > button:hover { border-color: var(--adv-accent); color: white; }
h1, h2, h3 { letter-spacing: -0.02em; }
h1 { color: var(--adv-accent); font-weight: 850; }
@media (max-width: 900px) {
    [data-testid="stHorizontalBlock"] { flex-wrap: wrap; }
    [data-testid="column"] { min-width: 220px; flex: 1 1 calc(50% - 1rem); }
}
@media (max-width: 640px) {
    .block-container { padding: 1.2rem 1rem 5rem; }
    [data-testid="column"] { min-width: 100%; flex: 1 1 100%; }
    [data-testid="stMetric"] { min-height: 94px; padding: 12px 14px; }
    h1 { font-size: 1.75rem; }
}
</style>
"""


def apply_command_center_theme(streamlit_module) -> None:
    """Apply static local CSS; no user content or external scripts are inserted."""
    streamlit_module.markdown(COMMAND_CENTER_CSS, unsafe_allow_html=True)
