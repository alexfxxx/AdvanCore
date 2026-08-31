import json
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_workspace_uses_allowlisted_segments_and_versioned_local_assets():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    javascript = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")

    for segment_id in (
        "controller",
        "readiness",
        "fleet",
        "dispatch",
        "fuel",
        "projects",
        "knowledge",
        "voice",
        "appearance",
        "governance",
    ):
        assert f'data-segment-id="{segment_id}"' in html
    for identifier in (
        "edit-workspace",
        "workspace-editor",
        "workspace-layout-list",
        "mobile-segment-select",
        "reset-workspace",
        "reset-display-layout",
    ):
        assert f'id="{identifier}"' in html
    assert "WORKSPACE_SEGMENT_CATALOG" in javascript
    assert "WORKSPACE_LAYOUT_KEY" in javascript
    assert "validatedWorkspaceLayout" in javascript
    assert "/assets/styles.css?v=task-174-1" in html
    assert "/assets/app.js?v=task-174-1" in html
    assert "/assets/editing.js?v=task-174-1" in html
    assert "Build task-174-1" in html


def test_layout_persistence_is_browser_local_and_has_no_network_or_write_action():
    javascript = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    block = javascript[
        javascript.index("function defaultWorkspacePreferences"):
        javascript.index("function updateMotionState")
    ]
    assert "localStorage.setItem" in block
    assert "localStorage.removeItem" in block
    assert "fetch(" not in block
    assert "requestJson(" not in block
    assert "controllerPost(" not in block
    assert "stored ? \"Layout saved only in this browser.\"" in block
    assert "browser storage is unavailable" in block


def test_workspace_css_has_supported_grid_sizes_drawer_and_mobile_switcher():
    css = (ROOT / "frontend" / "styles.css").read_text(encoding="utf-8")

    for size, columns in (("small", 4), ("medium", 6), ("wide", 8), ("full", 12)):
        assert f'data-segment-size="{size}"' in css
        assert f"span {columns}" in css
    assert ".detail-drawer" in css
    assert ".fleet-compact-row" in css
    assert '@media (max-width: 620px)' in css
    assert 'data-mobile-active="true"' in css


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is unavailable")
def test_workspace_validator_fails_closed_and_reordering_reaches_edges():
    javascript = ROOT / "frontend" / "app.js"
    node_script = r'''
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
const result = vm.runInContext(`(() => {
  const defaults = defaultWorkspacePreferences();
  const hostile = validatedWorkspaceLayout({
    version: 1,
    segments: defaults.segments.map((item, index) => index === 0
      ? {id: "<script>", visible: true, size: "wide"}
      : item),
  });
  const duplicate = validatedWorkspaceLayout({
    version: 1,
    segments: defaults.segments.map((item, index) => index === 1
      ? {...item, id: defaults.segments[0].id}
      : item),
  });
  const oldVersion = validatedWorkspaceLayout({...defaults, version: 0});
  const unsafeSize = validatedWorkspaceLayout({
    version: 1,
    segments: defaults.segments.map((item, index) => index === 0
      ? {...item, size: "oversized"}
      : item),
  });
  const resized = workspaceSegmentsWithUpdate(defaults.segments, "readiness", {size: "medium", visible: false});
  const replaced = replacedWorkspaceSegments(defaults.segments, "controller", "voice");
  return {
    defaultIds: defaults.segments.map((item) => item.id),
    hostileIds: hostile.segments.map((item) => item.id),
    duplicateIds: duplicate.segments.map((item) => item.id),
    oldVersionIds: oldVersion.segments.map((item) => item.id),
    unsafeSizeIds: unsafeSize.segments.map((item) => item.id),
    resized: resized.find((item) => item.id === "readiness"),
    replacedController: replaced.find((item) => item.id === "controller"),
    replacedVoice: replaced.find((item) => item.id === "voice"),
    replacementOrder: replaced.map((item) => item.id),
    down: reorderedWorkspaceSegmentIds(["a", "b", "c"], "a", "c"),
    up: reorderedWorkspaceSegmentIds(["a", "b", "c"], "c", "a"),
  };
})()`, context);
process.stdout.write(JSON.stringify(result));
'''
    completed = subprocess.run(
        [shutil.which("node"), "-e", node_script, str(javascript)],
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)
    assert result["hostileIds"] == result["defaultIds"]
    assert result["duplicateIds"] == result["defaultIds"]
    assert result["oldVersionIds"] == result["defaultIds"]
    assert result["unsafeSizeIds"] == result["defaultIds"]
    assert result["resized"] == {"id": "readiness", "visible": False, "size": "medium"}
    assert result["replacedController"]["visible"] is False
    assert result["replacedVoice"]["visible"] is True
    assert result["replacementOrder"][:2] == ["voice", "readiness"]
    assert result["replacementOrder"][7] == "controller"
    assert result["down"] == ["b", "c", "a"]
    assert result["up"] == ["c", "a", "b"]


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is unavailable")
def test_dashboard_summary_prioritises_active_then_recent_records():
    javascript = ROOT / "frontend" / "app.js"
    node_script = r'''
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
const records = [
  {id: "old-active", status: "active", updated_at: "2026-08-01T00:00:00Z"},
  {id: "new-archived", status: "archived", updated_at: "2026-08-30T00:00:00Z"},
  {id: "new-active", status: "active", updated_at: "2026-08-29T00:00:00Z"},
  {id: "new-superseded", status: "superseded", updated_at: "2026-08-31T00:00:00Z"},
  {id: "old-archived", status: "archived", updated_at: "2026-07-01T00:00:00Z"},
];
process.stdout.write(JSON.stringify(vm.runInContext(
  `recentActiveRecords(${JSON.stringify(records)}).map((item) => item.id)`,
  context,
)));
'''
    completed = subprocess.run(
        [shutil.which("node"), "-e", node_script, str(javascript)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(completed.stdout) == [
        "new-active",
        "old-active",
        "new-superseded",
        "new-archived",
        "old-archived",
    ]
