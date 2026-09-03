import json
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_primary_console_links_to_dedicated_fuel_reports():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")

    assert 'href="/fuel-reports"' in html
    assert "Fuel reports" in html


def test_fuel_report_page_has_explicit_draft_and_export_controls():
    html = (ROOT / "frontend" / "fuel-reports.html").read_text(encoding="utf-8")

    for identifier in (
        "report-customer",
        "report-service",
        "report-date-from",
        "report-date-to",
        "generate-fuel-report",
        "print-fuel-report",
        "download-fuel-csv",
        "fuel-report-document",
        "report-history-body",
    ):
        assert f'id="{identifier}"' in html
    assert "DRAFT INDICATION — NOT AN INVOICE" in html
    assert "NO DATABASE WRITES" in html
    assert "no automatic customer delivery" in html
    assert "/assets/fuel-reports.js?v=task-189-1" in html
    assert '<script src="http' not in html


def test_fuel_report_client_is_read_only_and_uses_existing_fact_endpoints():
    javascript = (ROOT / "frontend" / "fuel-reports.js").read_text(encoding="utf-8")

    assert 'requestJson("/api/customers")' in javascript
    assert "/recurring-services`" in javascript
    assert "/fuel-adjustment`" in javascript
    assert 'requestJson("/api/fuel/market-benchmark")' in javascript
    assert "window.print()" in javascript
    assert "reportCsvRows" in javascript
    assert "innerHTML" not in javascript
    assert 'method: "POST"' not in javascript
    assert "X-AdvanCore-Action-Token" not in javascript
    assert "/fuel-rules" not in javascript
    assert "financial-entries" not in javascript
    assert "mailto:" not in javascript
    assert "selectionRevision" in javascript
    assert "requestRevision !== selectionRevision" in javascript
    assert "benchmarkMatchesDraft" in javascript
    assert 'service.status !== "archived"' in javascript


def test_fuel_report_css_has_responsive_screen_and_print_layouts():
    css = (ROOT / "frontend" / "styles.css").read_text(encoding="utf-8")

    assert ".fuel-report-layout" in css
    assert ".fuel-report-document" in css
    assert ".report-history-table" in css
    assert "@media print" in css
    assert "#fuel-report-document" in css
    assert "@media (max-width: 860px)" in css


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is unavailable")
def test_csv_export_neutralises_formulas_and_quotes_fields():
    javascript = ROOT / "frontend" / "fuel-reports.js"
    node_script = r'''
const fs = require("fs");
const vm = require("vm");
const context = {
  document: { addEventListener: () => {} },
  console,
  Intl,
  URL,
  Blob,
  setTimeout,
};
vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[1], "utf8"), context);
const values = vm.runInContext(
  `[
    csvCell("=HYPERLINK(1)"),
    csvCell("+SUM(A1)"),
    csvCell("-10"),
    csvCell("@command"),
    csvCell('Customer "A"'),
  ]`,
  context,
);
process.stdout.write(JSON.stringify(values));
'''
    completed = subprocess.run(
        [shutil.which("node"), "-e", node_script, str(javascript)],
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(completed.stdout) == [
        '"\'=HYPERLINK(1)"',
        '"\'+SUM(A1)"',
        '"\'-10"',
        '"\'@command"',
        '"Customer ""A"""',
    ]


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is unavailable")
def test_report_rejects_benchmark_evidence_that_does_not_match_draft():
    javascript = ROOT / "frontend" / "fuel-reports.js"
    node_script = r'''
const fs = require("fs");
const vm = require("vm");
const context = {
  document: { addEventListener: () => {} },
  console,
  Intl,
  URL,
  Blob,
  setTimeout,
};
vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[1], "utf8"), context);
const results = vm.runInContext(`(() => {
  const draft = {benchmark_observed_on: "2026-09-03", benchmark_price_per_litre: "3.9200"};
const matching = {
    retrieved_on: "2026-09-03", median: "3.92", status: "current", stale: false,
    market_observations: [
      {provider: "Shell", price_per_litre: "3.95"},
      {provider: "SPC", price_per_litre: "3.89"},
    ],
  };
  const staleEvidence = {...matching, retrieved_on: "2026-09-02"};
  const failedRefresh = {...matching, status: "stale", stale: true};
  const missingProvider = {...matching, market_observations: [matching.market_observations[0]]};
  return [
    benchmarkMatchesDraft(draft, matching),
    benchmarkMatchesDraft(draft, staleEvidence),
    benchmarkMatchesDraft(draft, failedRefresh),
    benchmarkMatchesDraft(draft, missingProvider),
  ];
})()`, context);
process.stdout.write(JSON.stringify(results));
'''
    completed = subprocess.run(
        [shutil.which("node"), "-e", node_script, str(javascript)],
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(completed.stdout) == [True, False, False, False]
