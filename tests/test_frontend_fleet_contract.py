import json
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_decoupled_fleet_screen_exposes_only_bounded_filters():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    javascript = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")

    for identifier in ("fleet-company", "fleet-type", "fleet-capacity", "fleet-list"):
        assert f'id="{identifier}"' in html
    assert 'requestJson("/api/fleet' not in javascript
    assert "/api/fleet" in javascript
    assert "No sample records are generated" in javascript


def test_fleet_detail_preferences_are_allowlisted_browser_local_and_read_only():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    javascript = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")

    for identifier in ("fleet-field-layout", "reset-fleet-fields"):
        assert f'id="{identifier}"' in html
    assert "FLEET_FIELD_CATALOG" in javascript
    assert "FLEET_FIELD_PREFERENCE_KEY" in javascript
    assert "validatedFleetFieldPreferences" in javascript
    assert 'row.draggable = true' in javascript
    assert 'toggle.type = "checkbox"' in javascript
    assert "moveFleetField" in javascript
    preference_block = javascript[
        javascript.index("function saveFleetFieldPreferences"):
        javascript.index("function fleetFieldValue")
    ]
    assert "localStorage.setItem" in preference_block
    assert "fetch(" not in preference_block
    assert "requestJson(" not in preference_block


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is unavailable")
def test_drag_reordering_moves_down_up_and_into_final_position():
    javascript = ROOT / "frontend" / "app.js"
    node_script = r"""
const fs = require("fs");
const vm = require("vm");
const context = {
  document: { addEventListener: () => {} },
  console,
  Intl,
  URLSearchParams,
  setTimeout,
  clearTimeout,
};
vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[1], "utf8"), context);
const cases = [
  [["a", "b", "c"], "a", "b"],
  [["a", "b", "c"], "a", "c"],
  [["a", "b", "c"], "c", "a"],
];
const results = cases.map(([order, source, target]) => vm.runInContext(
  `reorderedFleetFieldIds(${JSON.stringify(order)}, ${JSON.stringify(source)}, ${JSON.stringify(target)})`,
  context,
));
process.stdout.write(JSON.stringify(results));
"""
    completed = subprocess.run(
        [shutil.which("node"), "-e", node_script, str(javascript)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(completed.stdout) == [
        ["b", "a", "c"],
        ["b", "c", "a"],
        ["c", "a", "b"],
    ]
