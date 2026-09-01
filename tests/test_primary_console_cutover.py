from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_port_8000_is_the_primary_app_and_streamlit_is_secondary():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    startup = (ROOT / "scripts" / "start-advancore.sh").read_text(encoding="utf-8")
    health = (ROOT / "scripts" / "check-local-interfaces.py").read_text(encoding="utf-8")

    assert "AdvanCore Main App" in html
    assert "PRIMARY LOCAL APP" in html
    assert "Your main AdvanCore workspace" in html
    assert "Temporary admin/editing" in html
    assert "http://127.0.0.1:8501/" in html
    assert "PRIMARY APP: http://127.0.0.1:8000" in startup
    assert "Temporary admin/editing interface: http://127.0.0.1:8501" in startup
    assert 'InterfaceCheck("Primary AdvanCore app"' in health
    assert "Open `http://127.0.0.1:8000` as the main AdvanCore app" in readme


def test_cutover_inventory_is_bounded_and_keeps_streamlit_until_transfer():
    cutover = (
        ROOT / "docs" / "architecture" / "PRIMARY_CONSOLE_CUTOVER.md"
    ).read_text(encoding="utf-8")

    for transferred in (
        "TASK-170 through TASK-179 completed the shared safe-editing boundary",
        "Projects, Knowledge, Fleet, Driver, Customer, Route, Trip, Assignment, Fuel and",
        "Finance transfers plus read-only Activity Log history",
        "No schema or business field was added",
    ):
        assert transferred in cutover
    for remaining_workflow in (
        "Settings/recovery: backup inventory, create/verify backup",
        "Dashboard AI readiness: the start-of-day Kimi, Gemini and Codex",
        "Dashboard AI workforce: most recently selected worker",
        "AI Center attention inbox: owner decisions and controller investigations",
        "AI Center routing status: selected implementation worker",
        "AI Center governance self-check: the offline multi-worker rehearsal",
        "AI Center Gemini readiness: candidate activation state",
    ):
        assert remaining_workflow in cutover
    for transfer in (
        "Start-of-day authentication readiness, selected-worker status",
        "AI attention inbox, offline governance self-check and Gemini readiness",
    ):
        assert transfer in cutover
    assert "Business rules must stay in services" in cutover
    assert "owner explicitly" in cutover
    assert "Port 8501 may be stopped by default only after" in cutover
