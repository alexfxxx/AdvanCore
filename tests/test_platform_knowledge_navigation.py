from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_business_record_views_are_status_scoped():
    editor = (ROOT / "frontend/editing.js").read_text()
    summary = (ROOT / "frontend/app.js").read_text()
    assert 'filter(record => record.status === "active")' in editor
    assert 'filter(record => record.status === "active")' in summary
    assert 'filter(record => record.status === "approved")' in summary
    assert 'if (!["approved", "draft"].includes(view)) view = "approved"' in editor
    assert 'filter(record => record.status === view)' in editor
    assert 'Drafts awaiting approval' in editor
    assert 'appendCompactForm(section, createForm, "Add business initiative")' in editor


def test_platform_and_operations_navigation_are_separate():
    editor = (ROOT / "frontend/editing.js").read_text()
    html = (ROOT / "frontend/index.html").read_text()
    css = (ROOT / "frontend/styles.css").read_text()
    assert '<body class="platform-mode">' in html
    assert 'aria-label="AdvanCore platform navigation"' in html
    assert 'classList.toggle("operations-mode", !platformWorkspace)' in editor
    assert 'manager.hidden = true' in editor
    assert 'body.operations-mode .platform-sidebar { display: none; }' in css
    assert '.manager-form[hidden] { display: none !important; }' in css
