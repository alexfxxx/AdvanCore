from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_dispatch_screen_is_dated_and_read_only():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    javascript = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")

    assert 'id="dispatch-date" type="date"' in html
    assert 'id="dispatch-list"' in html
    assert "/api/dispatch?service_date=" in javascript
    assert "available_vehicles" in javascript
    assert "available_drivers" in javascript
