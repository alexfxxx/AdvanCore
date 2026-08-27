from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_decoupled_fleet_screen_exposes_only_bounded_filters():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    javascript = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")

    for identifier in ("fleet-company", "fleet-type", "fleet-capacity", "fleet-list"):
        assert f'id="{identifier}"' in html
    assert 'requestJson("/api/fleet' not in javascript
    assert "/api/fleet" in javascript
    assert "No sample records are generated" in javascript
