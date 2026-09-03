"use strict";

const byId = (id) => document.getElementById(id);
const DISPLAY_PREFERENCE_KEY = "advancore.console.preferences.v1";
const ALLOWED_THEMES = new Set(["midnight", "light-business", "graphite"]);
let customers = [];
let services = [];
let benchmark = null;
let currentReport = null;
let selectionRevision = 0;

async function requestJson(path) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || `Local API request failed (${response.status}).`);
  return payload;
}

function setStatus(message, tone = "neutral") {
  const status = byId("fuel-report-status");
  status.textContent = message;
  status.dataset.tone = tone;
}

function setText(id, value) {
  byId(id).textContent = value ?? "—";
}

function formatMoney(value, currency = "SGD") {
  if (value === null || value === undefined || value === "") return "Not available";
  return new Intl.NumberFormat("en-SG", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number(value));
}

function formatPrice(value) {
  if (value === null || value === undefined || value === "") return "Not available";
  return `${formatMoney(value)}/L`;
}

function formatPercent(value) {
  if (value === null || value === undefined || value === "") return "Not available";
  return `${Number(value).toLocaleString("en-SG", { maximumFractionDigits: 4 })}%`;
}

function replaceOptions(select, options, placeholder) {
  select.replaceChildren();
  const first = document.createElement("option");
  first.value = "";
  first.textContent = placeholder;
  select.append(first);
  options.forEach(({ value, label }) => {
    const option = document.createElement("option");
    option.value = String(value);
    option.textContent = label;
    select.append(option);
  });
}

function clearReport() {
  currentReport = null;
  byId("fuel-report-document").hidden = true;
  byId("fuel-report-empty").hidden = false;
  byId("print-fuel-report").disabled = true;
  byId("download-fuel-csv").disabled = true;
}

function invalidateReport() {
  selectionRevision += 1;
  clearReport();
}

function configureEvidenceDates() {
  const history = Array.isArray(benchmark?.history) ? benchmark.history : [];
  if (!history.length) return;
  const dates = history.map((item) => item.observed_on).sort();
  const from = byId("report-date-from");
  const to = byId("report-date-to");
  from.min = dates[0];
  from.max = dates[dates.length - 1];
  to.min = dates[0];
  to.max = dates[dates.length - 1];
  if (!from.value) from.value = dates[0];
  if (!to.value) to.value = dates[dates.length - 1];
}

function filteredHistory(sourceBenchmark, from, to) {
  if (from && to && from > to) throw new Error("Evidence start date must not be after the end date.");
  return (sourceBenchmark.history || []).filter((item) => (
    (!from || item.observed_on >= from) && (!to || item.observed_on <= to)
  ));
}

function benchmarkMatchesDraft(draft, sourceBenchmark) {
  if (Boolean(sourceBenchmark.stale) !== Boolean(draft.stale)) return false;
  if (
    draft.calculation_status === "draft_ready"
    && (sourceBenchmark.status !== "current" || sourceBenchmark.stale)
  ) return false;
  if (draft.benchmark_observed_on === null || draft.benchmark_price_per_litre === null) {
    return sourceBenchmark.retrieved_on === null && sourceBenchmark.median === null;
  }
  const observations = Array.isArray(sourceBenchmark.market_observations)
    ? sourceBenchmark.market_observations
    : [];
  const providers = new Set(observations.map((item) => item.provider));
  const pricesAreValid = observations.every((item) => Number.isFinite(Number(item.price_per_litre)) && Number(item.price_per_litre) > 0);
  return sourceBenchmark.retrieved_on === draft.benchmark_observed_on
    && Number(sourceBenchmark.median) === Number(draft.benchmark_price_per_litre)
    && observations.length === 2
    && providers.has("Shell")
    && providers.has("SPC")
    && pricesAreValid;
}

function safeSourceLink(observation) {
  const link = document.createElement("a");
  link.className = "source-link";
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.textContent = observation.source_name;
  try {
    const url = new URL(observation.source_url);
    if (url.protocol === "https:") link.href = url.href;
  } catch (_error) {
    link.removeAttribute("href");
  }
  return link;
}

function renderSources() {
  const container = byId("report-source-list");
  container.replaceChildren();
  (benchmark.market_observations || []).forEach((observation) => {
    const item = document.createElement("article");
    item.className = "report-source-card";
    const heading = document.createElement("strong");
    heading.textContent = `${observation.provider} · ${observation.grade}`;
    const price = document.createElement("span");
    price.textContent = formatPrice(observation.price_per_litre);
    const updated = document.createElement("small");
    updated.textContent = `Source updated: ${observation.source_updated_at}`;
    item.append(heading, price, updated, safeSourceLink(observation));
    container.append(item);
  });
}

function renderHistory(history) {
  const body = byId("report-history-body");
  body.replaceChildren();
  history.forEach((item) => {
    const row = document.createElement("tr");
    [
      item.observed_on,
      formatPrice(item.shell_price_per_litre),
      formatPrice(item.spc_price_per_litre),
      formatPrice(item.benchmark_price_per_litre),
    ].forEach((value) => {
      const cell = document.createElement("td");
      cell.textContent = value;
      row.append(cell);
    });
    body.append(row);
  });
  byId("report-history-empty").hidden = history.length > 0;
  byId("report-evidence-window").textContent = history.length
    ? `${history.length} verified daily benchmark record${history.length === 1 ? "" : "s"} in the selected evidence window.`
    : "No stored daily benchmark matches the selected evidence window.";
}

function calculationMessage(draft) {
  const messages = {
    contract_terms_not_configured: "Draft unavailable: this service has no saved contract fuel terms.",
    benchmark_stale: "Draft unavailable: the last verified benchmark is stale.",
    benchmark_unavailable: "Draft unavailable: no verified Shell/SPC benchmark is available.",
  };
  if (draft.calculation_status === "draft_ready") {
    return "Calculated from the saved fixed monthly amount, fuel-cost share, contract baseline and current verified midpoint. This remains a draft indication.";
  }
  return messages[draft.calculation_status] || "Draft unavailable: the saved information is incomplete or cannot be verified.";
}

function renderReport(customer, service, draft, history) {
  const rule = draft.current_rule;
  const ready = draft.calculation_status === "draft_ready" && !draft.stale;
  setText("report-generated-on", new Intl.DateTimeFormat("en-SG", { dateStyle: "long" }).format(new Date()));
  setText("report-benchmark-date", draft.benchmark_observed_on || "Not available");
  setText("report-customer-name", customer.name);
  setText("report-service-reference", service.service_reference);
  setText("report-service-status", service.status);
  setText("report-monthly-contract", formatMoney(service.monthly_amount, service.currency_code));
  setText("report-benchmark-price", formatPrice(draft.benchmark_price_per_litre));
  setText("report-price-variance", ready ? formatPercent(draft.price_variance_percent) : "Not calculated");
  setText("report-adjustment", ready ? formatMoney(draft.draft_adjustment_amount, service.currency_code) : "Not calculated");
  setText("report-adjusted-total", ready ? formatMoney(draft.adjusted_monthly_amount, service.currency_code) : "Not calculated");
  setText("report-rule-effective", rule?.effective_from || "Not configured");
  setText("report-baseline", rule ? formatPrice(rule.baseline_price_per_litre) : "Not configured");
  setText("report-fuel-share", rule ? formatPercent(rule.fuel_cost_share_percent) : "Not configured");
  setText("report-tolerance", rule ? formatPercent(rule.tolerance_percent) : "Not configured");
  setText("report-calculation-status", calculationMessage(draft));
  setText(
    "report-formula",
    rule
      ? "Price variance = (Shell–SPC midpoint − contract baseline) ÷ contract baseline. When the absolute variance exceeds the saved tolerance, draft adjustment = fixed monthly amount × saved fuel share × price variance."
      : "No formula has been applied because this recurring service has no saved contract fuel terms.",
  );
  byId("report-calculation-status").dataset.state = ready ? "ready" : "unavailable";
  renderSources();
  renderHistory(history);
  byId("fuel-report-empty").hidden = true;
  byId("fuel-report-document").hidden = false;
  byId("print-fuel-report").disabled = false;
  byId("download-fuel-csv").disabled = false;
  currentReport = { customer, service, draft, history };
}

async function loadServices(customerId) {
  invalidateReport();
  const requestRevision = selectionRevision;
  const serviceSelect = byId("report-service");
  const generate = byId("generate-fuel-report");
  serviceSelect.disabled = true;
  generate.disabled = true;
  replaceOptions(serviceSelect, [], "Loading recurring services…");
  if (!customerId) {
    replaceOptions(serviceSelect, [], "Select a customer first");
    setStatus("Select a saved customer to continue.");
    return;
  }
  try {
    const loadedServices = await requestJson(`/api/customers/${encodeURIComponent(customerId)}/recurring-services`);
    if (
      requestRevision !== selectionRevision
      || byId("report-customer").value !== String(customerId)
    ) return;
    services = loadedServices.filter((service) => service.status !== "archived");
    replaceOptions(
      serviceSelect,
      services.map((service) => ({
        value: service.id,
        label: `${service.service_reference} · ${service.status} · ${service.currency_code} ${service.monthly_amount} monthly`,
      })),
      services.length ? "Select a recurring service" : "No recurring services recorded",
    );
    serviceSelect.disabled = services.length === 0;
    setStatus(
      services.length
        ? "Select the recurring service to report."
        : "This customer has no recurring services. Add one in Manage records before generating a fuel report.",
      services.length ? "neutral" : "error",
    );
  } catch (error) {
    if (
      requestRevision !== selectionRevision
      || byId("report-customer").value !== String(customerId)
    ) return;
    replaceOptions(serviceSelect, [], "Recurring services unavailable");
    setStatus(error.message, "error");
  }
}

async function generateReport(event) {
  event.preventDefault();
  invalidateReport();
  const requestRevision = selectionRevision;
  const customerId = Number(byId("report-customer").value);
  const serviceId = Number(byId("report-service").value);
  const from = byId("report-date-from").value;
  const to = byId("report-date-to").value;
  const customer = customers.find((item) => item.id === customerId);
  const service = services.find((item) => item.id === serviceId);
  if (!customer || !service) {
    setStatus("Select an existing customer and recurring service.", "error");
    return;
  }
  try {
    if (from && to && from > to) throw new Error("Evidence start date must not be after the end date.");
    setStatus("Reading the saved contract and verified benchmark…");
    const [draft, freshBenchmark] = await Promise.all([
      requestJson(`/api/recurring-services/${service.id}/fuel-adjustment`),
      requestJson("/api/fuel/market-benchmark"),
    ]);
    if (
      requestRevision !== selectionRevision
      || byId("report-customer").value !== String(customerId)
      || byId("report-service").value !== String(serviceId)
      || byId("report-date-from").value !== from
      || byId("report-date-to").value !== to
    ) return;
    if (service.customer_id !== customer.id || draft.recurring_service_id !== service.id) {
      throw new Error("The selected customer and recurring service no longer match. Select them again.");
    }
    if (service.status === "archived") {
      throw new Error("Archived recurring services cannot produce a current fuel report.");
    }
    if (!benchmarkMatchesDraft(draft, freshBenchmark)) {
      throw new Error("The benchmark changed while this report was being prepared. Generate it again to use one verified evidence set.");
    }
    benchmark = freshBenchmark;
    const history = filteredHistory(freshBenchmark, from, to);
    renderReport(customer, service, draft, history);
    setStatus(
      draft.calculation_status === "draft_ready" && !draft.stale
        ? "Draft fuel report generated from saved facts. Review it before sharing."
        : calculationMessage(draft),
      draft.calculation_status === "draft_ready" && !draft.stale ? "success" : "error",
    );
  } catch (error) {
    if (
      requestRevision !== selectionRevision
      || byId("report-customer").value !== String(customerId)
      || byId("report-service").value !== String(serviceId)
      || byId("report-date-from").value !== from
      || byId("report-date-to").value !== to
    ) return;
    setStatus(error.message, "error");
  }
}

function csvCell(value) {
  let text = String(value ?? "");
  if (/^[=+\-@]/.test(text)) text = `'${text}`;
  return `"${text.replaceAll('"', '""')}"`;
}

function reportCsvRows(report) {
  const { customer, service, draft, history } = report;
  const rule = draft.current_rule;
  const ready = draft.calculation_status === "draft_ready" && !draft.stale;
  const rows = [
    ["AdvanCore Customer Fuel Adjustment Report", "DRAFT INDICATION — NOT AN INVOICE"],
    ["Customer", customer.name],
    ["Service reference", service.service_reference],
    ["Service status", service.status],
    ["Fixed monthly contract", service.monthly_amount, service.currency_code],
    ["Benchmark date", draft.benchmark_observed_on || "Not available"],
    ["Shell-SPC midpoint SGD/L", draft.benchmark_price_per_litre || "Not available"],
    ["Calculation status", draft.calculation_status],
    ["Contract baseline SGD/L", rule?.baseline_price_per_litre || "Not configured"],
    ["Fuel share percent", rule?.fuel_cost_share_percent || "Not configured"],
    ["Contract tolerance percent", rule?.tolerance_percent || "Not configured"],
    ["Price variance percent", ready ? draft.price_variance_percent : "Not calculated"],
    ["Draft adjustment", ready ? draft.draft_adjustment_amount : "Not calculated", service.currency_code],
    ["Indicated monthly total", ready ? draft.adjusted_monthly_amount : "Not calculated", service.currency_code],
    [],
    ["Verified benchmark history"],
    ["Date", "Shell diesel SGD/L", "SPC diesel SGD/L", "Midpoint SGD/L"],
    ...history.map((item) => [
      item.observed_on,
      item.shell_price_per_litre,
      item.spc_price_per_litre,
      item.benchmark_price_per_litre,
    ]),
  ];
  return rows.map((row) => row.map(csvCell).join(",")).join("\r\n");
}

function downloadCsv() {
  if (!currentReport) return;
  const blob = new Blob([reportCsvRows(currentReport)], { type: "text/csv;charset=utf-8" });
  const link = document.createElement("a");
  const safeName = currentReport.customer.name.replace(/[^a-z0-9]+/gi, "-").replace(/^-|-$/g, "").slice(0, 60) || "customer";
  const objectUrl = URL.createObjectURL(blob);
  link.href = objectUrl;
  link.download = `${safeName}-fuel-report.csv`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
}

function applyStoredTheme() {
  try {
    const stored = JSON.parse(localStorage.getItem(DISPLAY_PREFERENCE_KEY));
    if (stored && ALLOWED_THEMES.has(stored.theme)) document.documentElement.dataset.theme = stored.theme;
  } catch (_error) {
    // A missing or blocked browser store leaves the safe default theme intact.
  }
}

async function initialise() {
  applyStoredTheme();
  clearReport();
  byId("fuel-report-form").addEventListener("submit", generateReport);
  byId("report-customer").addEventListener("change", (event) => loadServices(event.target.value));
  byId("report-service").addEventListener("change", (event) => {
    invalidateReport();
    byId("generate-fuel-report").disabled = !event.target.value;
    if (event.target.value) setStatus("Ready to generate a read-only draft report.");
  });
  byId("report-date-from").addEventListener("change", invalidateReport);
  byId("report-date-to").addEventListener("change", invalidateReport);
  byId("print-fuel-report").addEventListener("click", () => {
    if (currentReport) window.print();
  });
  byId("download-fuel-csv").addEventListener("click", downloadCsv);

  try {
    [customers, benchmark] = await Promise.all([
      requestJson("/api/customers"),
      requestJson("/api/fuel/market-benchmark"),
    ]);
    configureEvidenceDates();
    const customerSelect = byId("report-customer");
    replaceOptions(
      customerSelect,
      customers.map((customer) => ({ value: customer.id, label: customer.name })),
      customers.length ? "Select a customer" : "No customers recorded",
    );
    customerSelect.disabled = customers.length === 0;
    setStatus(
      customers.length
        ? "Select a saved customer to continue."
        : "No customers are recorded. Add a customer and recurring service in Manage records first.",
      customers.length ? "neutral" : "error",
    );
  } catch (error) {
    replaceOptions(byId("report-customer"), [], "Customer records unavailable");
    setStatus(error.message, "error");
  }
}

document.addEventListener("DOMContentLoaded", initialise);
