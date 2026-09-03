from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_fuel_screen_labels_market_rates_and_sources():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    javascript = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    editing = (ROOT / "frontend" / "editing.js").read_text(encoding="utf-8")

    assert "gross rates before discounts" in html
    assert "Shell–SPC midpoint" in html
    assert "once per Singapore day" in html
    assert "/api/fuel/intelligence" in javascript
    assert "/api/fuel/market-benchmark" in javascript
    assert "source_updated_at" in javascript
    assert "renderFuelHistory" in javascript
    assert 'benchmark.status === "current"' in javascript
    assert 'rel = "noopener noreferrer"' in javascript
    assert "/fuel-adjustment" in editing
    assert "/fuel-rules" in editing
    assert "No default is assumed" in editing
    assert "never creates an invoice" in editing
