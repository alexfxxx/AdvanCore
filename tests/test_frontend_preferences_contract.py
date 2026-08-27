from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_display_preferences_are_allowlisted_and_browser_local():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    javascript = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    css = (ROOT / "frontend" / "styles.css").read_text(encoding="utf-8")

    assert 'value="light-business"' in html
    assert 'value="graphite"' in html
    assert "DISPLAY_ALLOWLIST" in javascript
    assert "localStorage.setItem" in javascript
    assert "fetch(" not in javascript[javascript.index("function applyPreferences"):javascript.index("function configurePreferences")]
    assert 'html[data-theme="light-business"]' in css
    assert 'html[data-motion="reduced"]' in css
