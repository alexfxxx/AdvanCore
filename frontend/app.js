"use strict";

const byId = (id) => document.getElementById(id);
let localActionToken = null;
let approvedPreviewGoal = null;
let activeRunId = null;
let progressStream = null;
const DISPLAY_PREFERENCE_KEY = "advancore.console.preferences.v1";
const DISPLAY_ALLOWLIST = {
  theme: ["midnight", "light-business", "graphite"],
  shape: ["soft", "compact"],
  motion: ["full", "reduced"],
};

async function requestJson(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || `Local API request failed (${response.status}).`);
  }
  return payload;
}

function setText(id, value) {
  const element = byId(id);
  if (element) element.textContent = value;
}

function showConnection(state, label) {
  const chip = byId("connection-chip");
  chip.classList.toggle("degraded", state !== "ready");
  setText("connection-label", label);
}

function recordRow(title, meta, status) {
  const row = document.createElement("article");
  row.className = "record-row";

  const copy = document.createElement("div");
  const heading = document.createElement("h3");
  heading.className = "record-title";
  heading.textContent = title;
  const detail = document.createElement("span");
  detail.className = "record-meta";
  detail.textContent = meta;
  copy.append(heading, detail);

  const badge = document.createElement("span");
  badge.className = "record-status";
  badge.textContent = status;
  row.append(copy, badge);
  return row;
}

function renderRecords(containerId, records, factory, emptyLabel) {
  const container = byId(containerId);
  container.replaceChildren();
  if (!records.length) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = emptyLabel;
    container.append(empty);
    return;
  }
  records.forEach((record) => container.append(factory(record)));
}

function formatMoney(value) {
  if (value === null || value === undefined || value === "") return "Not recorded";
  return new Intl.NumberFormat("en-SG", { style: "currency", currency: "SGD" }).format(Number(value));
}

function appendDetail(grid, label, value) {
  const item = document.createElement("div");
  const term = document.createElement("span");
  const result = document.createElement("strong");
  term.textContent = label;
  result.textContent = value ?? "Not recorded";
  item.append(term, result);
  grid.append(item);
}

function vehicleCard(vehicle, companies) {
  const card = document.createElement("article");
  card.className = "operation-card";
  const heading = document.createElement("div");
  heading.className = "operation-card-heading";
  const title = document.createElement("h3");
  title.textContent = vehicle.registration_number;
  const badge = document.createElement("span");
  badge.className = "record-status";
  badge.textContent = vehicle.status;
  heading.append(title, badge);
  const owner = companies.find((item) => item.id === vehicle.registered_owner_id);
  const grid = document.createElement("div");
  grid.className = "detail-grid";
  appendDetail(grid, "Registered owner", owner?.name || "Not recorded");
  appendDetail(grid, "Make / model", vehicle.make_model || "Not recorded");
  appendDetail(grid, "Vehicle / seating", [vehicle.vehicle_type, vehicle.passenger_capacity ? `${vehicle.passenger_capacity} seats` : null].filter(Boolean).join(" · ") || "Not recorded");
  appendDetail(grid, "Year / propellant", [vehicle.manufacture_year, vehicle.propellant].filter(Boolean).join(" · ") || "Not recorded");
  appendDetail(grid, "Parking", [vehicle.parking_provider, vehicle.parking_location, formatMoney(vehicle.parking_monthly_cost)].filter((item) => item && item !== "Not recorded").join(" · ") || "Not recorded");
  appendDetail(grid, "Insurance", [vehicle.insurance_provider, formatMoney(vehicle.insurance_annual_amount)].filter((item) => item && item !== "Not recorded").join(" · ") || "Not recorded");
  appendDetail(grid, "Road tax", vehicle.road_tax_amount === null ? "Not recorded" : `${formatMoney(vehicle.road_tax_amount)} / ${vehicle.road_tax_period_months} months`);
  appendDetail(grid, "COE expiry", vehicle.coe_expiry || "Not recorded");
  card.append(heading, grid);
  return card;
}

function replaceOptions(select, records, valueFor, labelFor, firstLabel) {
  const selected = select.value;
  select.replaceChildren();
  const first = document.createElement("option");
  first.value = "";
  first.textContent = firstLabel;
  select.append(first);
  records.forEach((record) => {
    const option = document.createElement("option");
    option.value = valueFor(record);
    option.textContent = labelFor(record);
    select.append(option);
  });
  if ([...select.options].some((option) => option.value === selected)) select.value = selected;
}

async function loadFleet({ initialiseFilters = false } = {}) {
  const parameters = new URLSearchParams();
  const company = byId("fleet-company").value;
  const type = byId("fleet-type").value;
  const capacity = byId("fleet-capacity").value;
  if (company) parameters.set("registered_owner_id", company);
  if (type) parameters.set("vehicle_type", type);
  if (capacity) parameters.set("passenger_capacity", capacity);
  const path = `/api/fleet${parameters.size ? `?${parameters}` : ""}`;
  try {
    const fleet = await requestJson(path);
    if (initialiseFilters) {
      replaceOptions(byId("fleet-company"), fleet.companies, (item) => String(item.id), (item) => item.name, "All companies");
      const capacities = [...new Set(fleet.vehicles.map((item) => item.passenger_capacity).filter(Boolean))].sort((a, b) => a - b);
      replaceOptions(byId("fleet-capacity"), capacities, String, (item) => `${item} seats`, "All capacities");
    }
    setText("fleet-summary", `${fleet.vehicles.length} vehicle${fleet.vehicles.length === 1 ? "" : "s"} shown. No sample records are generated.`);
    renderRecords("fleet-list", fleet.vehicles, (vehicle) => vehicleCard(vehicle, fleet.companies), "No vehicles match these filters.");
  } catch (error) {
    setText("fleet-summary", error.message);
    renderRecords("fleet-list", [], recordRow, "Fleet is unavailable.");
  }
}

function dispatchCard(row) {
  const card = document.createElement("article");
  card.className = `operation-card${row.conflicts.length ? " has-conflict" : ""}`;
  const heading = document.createElement("div");
  heading.className = "operation-card-heading";
  const title = document.createElement("h3");
  title.textContent = row.trip_reference;
  const badge = document.createElement("span");
  badge.className = "record-status";
  badge.textContent = row.dispatch_state;
  heading.append(title, badge);
  const route = document.createElement("p");
  route.className = "route-label";
  route.textContent = row.route_label;
  const grid = document.createElement("div");
  grid.className = "detail-grid three-columns";
  appendDetail(grid, "Trip state", row.trip_status);
  appendDetail(grid, "Vehicle", row.vehicle_label);
  appendDetail(grid, "Driver", row.driver_label);
  card.append(heading, route, grid);
  row.conflicts.forEach((message) => {
    const conflict = document.createElement("p");
    conflict.className = "conflict-copy";
    conflict.textContent = message;
    card.append(conflict);
  });
  return card;
}

async function loadDispatch() {
  const serviceDate = byId("dispatch-date").value;
  if (!serviceDate) return;
  try {
    const board = await requestJson(`/api/dispatch?service_date=${encodeURIComponent(serviceDate)}`);
    setText("dispatch-trip-count", board.trip_count);
    setText("dispatch-conflict-count", board.conflict_count);
    setText("dispatch-vehicle-count", board.available_vehicles.length);
    setText("dispatch-driver-count", board.available_drivers.length);
    renderRecords("dispatch-list", board.rows, dispatchCard, "No trips are recorded for this date.");
  } catch (error) {
    renderRecords("dispatch-list", [], recordRow, error.message);
  }
}

function fuelPriceRow(observation) {
  const row = recordRow(
    `${observation.provider} · ${observation.grade}`,
    observation.source_updated_at,
    `${formatMoney(observation.price_per_litre)}/L`,
  );
  const link = document.createElement("a");
  link.href = observation.source_url;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.className = "source-link";
  link.textContent = observation.source_name;
  row.querySelector("div").append(link);
  return row;
}

async function loadFuel() {
  try {
    const [intelligence, benchmark] = await Promise.all([
      requestJson("/api/fuel/intelligence"),
      requestJson("/api/fuel/market-benchmark"),
    ]);
    setText("fuel-entry-count", intelligence.entry_count);
    setText("fuel-total-litres", `${Number(intelligence.total_litres).toLocaleString("en-SG")} L`);
    setText("fuel-market-median", `${formatMoney(benchmark.median)}/L`);
    setText("fuel-market-range", `${formatMoney(benchmark.low)}–${formatMoney(benchmark.high)}/L`);
    setText("fuel-market-date", `${benchmark.benchmark_grade} · ${benchmark.basis} · retrieved ${benchmark.retrieved_on}`);
    renderRecords("fuel-market-list", benchmark.market_observations, fuelPriceRow, "No market observations recorded.");
    renderRecords("fuel-official-list", benchmark.official_confirmations, fuelPriceRow, "No official confirmations recorded.");
  } catch (error) {
    setText("fuel-market-date", error.message);
    renderRecords("fuel-market-list", [], recordRow, "Fuel market reference is unavailable.");
    renderRecords("fuel-official-list", [], recordRow, "Official price checks are unavailable.");
  }
}

function validatedPreferences(raw) {
  const defaults = { theme: "midnight", shape: "soft", motion: "full" };
  if (!raw || typeof raw !== "object") return defaults;
  return Object.fromEntries(Object.entries(defaults).map(([key, fallback]) => [
    key,
    DISPLAY_ALLOWLIST[key].includes(raw[key]) ? raw[key] : fallback,
  ]));
}

function applyPreferences(preferences) {
  const safe = validatedPreferences(preferences);
  document.documentElement.dataset.theme = safe.theme;
  document.documentElement.dataset.shape = safe.shape;
  document.documentElement.dataset.motion = safe.motion;
  Object.entries(safe).forEach(([key, value]) => {
    const select = byId(`preference-${key}`);
    if (select) select.value = value;
  });
  localStorage.setItem(DISPLAY_PREFERENCE_KEY, JSON.stringify(safe));
}

function configurePreferences() {
  let stored = null;
  try { stored = JSON.parse(localStorage.getItem(DISPLAY_PREFERENCE_KEY)); } catch (_error) { stored = null; }
  applyPreferences(stored);
  ["theme", "shape", "motion"].forEach((key) => {
    byId(`preference-${key}`).addEventListener("change", () => applyPreferences({
      theme: byId("preference-theme").value,
      shape: byId("preference-shape").value,
      motion: byId("preference-motion").value,
    }));
  });
  byId("reset-preferences").addEventListener("click", () => applyPreferences(null));
}

async function loadStatus() {
  try {
    const status = await requestJson("/api/status");
    showConnection(status.state, status.state === "ready" ? "Local API ready" : "Local API degraded");
    setText("database-state", status.database_reachable ? "Reachable" : "Unavailable");
    setText("controller-state", status.controller_available ? "Available" : "Unavailable");
    setText("governance-state", status.governance_mode.replace("_", " "));
    setText("voice-state", status.voice_state);
  } catch (error) {
    showConnection("degraded", "Local API unavailable");
    setText("database-state", "Unavailable");
    setText("controller-state", "Unavailable");
  }
}

async function loadProjects() {
  try {
    const projects = await requestJson("/api/projects");
    renderRecords(
      "projects-list",
      projects,
      (project) => recordRow(project.name, project.description || "No description recorded", project.status),
      "No projects recorded.",
    );
  } catch (error) {
    renderRecords("projects-list", [], recordRow, error.message);
  }
}

async function loadKnowledge() {
  try {
    const items = await requestJson("/api/knowledge");
    renderRecords(
      "knowledge-list",
      items,
      (item) => recordRow(item.title, `Project ${item.project_id ?? "not linked"}`, item.status),
      "No Knowledge items recorded.",
    );
  } catch (error) {
    renderRecords("knowledge-list", [], recordRow, error.message);
  }
}

function showGoalResult(message, isError = false) {
  const result = byId("goal-result");
  result.hidden = false;
  result.classList.toggle("error", isError);
  result.textContent = message;
}

async function loadLocalActionSession() {
  const session = await requestJson("/api/session");
  localActionToken = session.action_token;
  if (approvedPreviewGoal) byId("start-goal").disabled = false;
}

async function controllerPost(path, payload) {
  if (!localActionToken) {
    await loadLocalActionSession();
  }
  return requestJson(path, {
    method: "POST",
    headers: { "X-AdvanCore-Action-Token": localActionToken },
    body: JSON.stringify(payload),
  });
}

function setControllerActions(status, runId) {
  const panel = byId("controller-actions");
  const resume = byId("resume-controller");
  activeRunId = runId || activeRunId;
  panel.hidden = true;
  resume.hidden = true;
  panel.querySelectorAll("button").forEach((button) => {
    const action = button.dataset.ownerAction;
    const taskAction = action === "APPROVE_TASK" || action === "BLOCK_TASK";
    button.hidden = status === "AWAITING_TASK_APPROVAL" ? !taskAction : taskAction;
  });
  if (status === "AWAITING_TASK_APPROVAL" || status === "AWAITING_IMPLEMENTATION_DECISION") {
    panel.hidden = false;
  } else if (activeRunId && status && !["PUBLISHED", "BLOCKED"].includes(status)) {
    resume.hidden = false;
  }
}

function renderProgress(snapshot) {
  byId("progress-panel").hidden = false;
  setText("progress-state", snapshot.state || snapshot.status || "Working");
  setText("progress-run", snapshot.run_id || "Pending assignment");
  setText("progress-task", snapshot.task_id || "Pending assignment");
  setText("progress-phase", snapshot.phase || "Controller intake");
  setText("progress-message", snapshot.message || "Controller is working.");
  setText("progress-next", snapshot.next_action ? `Next: ${snapshot.next_action}` : "");
  if (snapshot.run_id) activeRunId = snapshot.run_id;
  if (snapshot.terminal) {
    setControllerActions(snapshot.status, snapshot.run_id);
  } else {
    byId("controller-actions").hidden = true;
    byId("resume-controller").hidden = true;
  }
}

function watchProgress(job) {
  renderProgress(job);
  if (progressStream) progressStream.close();
  progressStream = new EventSource(job.events_url);
  progressStream.addEventListener("progress", (event) => {
    const snapshot = JSON.parse(event.data);
    renderProgress(snapshot);
    if (snapshot.terminal) {
      progressStream.close();
      progressStream = null;
    }
  });
  progressStream.onerror = () => {
    if (progressStream) progressStream.close();
    progressStream = null;
    setText("progress-message", "Live connection closed. The checkpoint remains available to the controller.");
  };
}

async function recoverCurrentJob() {
  try {
    const job = await requestJson("/api/orchestration-jobs/current");
    if (job.terminal) {
      renderProgress(job);
    } else {
      watchProgress(job);
    }
  } catch (error) {
    if (!error.message.includes("not found") && !error.message.includes("No orchestration job")) {
      console.warn("Current governed job could not be restored.");
    }
  }
}

function confirmControllerRequest(message) {
  return window.confirm(`${message}\n\nThis request still follows agent_runner governance and may stop for another owner decision.`);
}

async function launchGoal(input) {
  if (!approvedPreviewGoal || approvedPreviewGoal !== input.value) {
    showGoalResult("Preview the current goal before starting it.", true);
    return;
  }
  if (!confirmControllerRequest("Start this governed goal through the controller?")) return;
  const startButton = byId("start-goal");
  startButton.disabled = true;
  try {
    const job = await controllerPost("/api/orchestrations", {
      goal: input.value,
      confirmed: true,
    });
    watchProgress(job);
    showGoalResult("Controller request accepted. Live progress is shown below.");
  } catch (error) {
    showGoalResult(error.message, true);
  } finally {
    startButton.disabled = false;
  }
}

async function submitOwnerAction(action) {
  if (!activeRunId) return;
  const publicationNotice = action === "APPROVE_IMPLEMENTATION"
    ? " This may allow verified feature-branch publication; it never permits a merge to main."
    : "";
  if (!confirmControllerRequest(`Submit ${action.replaceAll("_", " ").toLowerCase()}?${publicationNotice}`)) return;
  try {
    const job = await controllerPost(`/api/orchestrations/${encodeURIComponent(activeRunId)}/actions`, {
      action,
      confirmed: true,
    });
    watchProgress(job);
  } catch (error) {
    setText("progress-message", error.message);
  }
}

async function resumeController() {
  if (!activeRunId || !confirmControllerRequest("Resume this run from its governed checkpoint?")) return;
  try {
    const job = await controllerPost(`/api/orchestrations/${encodeURIComponent(activeRunId)}/resume`, {
      confirmed: true,
    });
    watchProgress(job);
  } catch (error) {
    setText("progress-message", error.message);
  }
}

function configureGoalForm() {
  const form = byId("owner-goal-form");
  const input = byId("owner-goal");
  const previewButton = byId("preview-goal");
  const startButton = byId("start-goal");

  input.addEventListener("input", () => {
    setText("goal-count", `${input.value.length} / 2000`);
    approvedPreviewGoal = null;
    startButton.disabled = true;
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    previewButton.disabled = true;
    startButton.disabled = true;
    showGoalResult("Validating through the governed dry-run controller…");
    try {
      const preview = await requestJson("/api/orchestrations/preview", {
        method: "POST",
        body: JSON.stringify({ goal: input.value }),
      });
      const lines = [
        `Status: ${preview.status}`,
        `Candidate task: ${preview.task_id || "not assigned"}`,
        `Files changed: ${preview.mutations_performed.length ? preview.mutations_performed.join(", ") : "none"}`,
        `Worker launched: ${preview.worker_launched ? "yes" : "no"}`,
        `Next: ${preview.next_action}`,
      ];
      showGoalResult(lines.join("\n"));
      approvedPreviewGoal = input.value;
      startButton.disabled = !localActionToken;
    } catch (error) {
      showGoalResult(error.message, true);
    } finally {
      previewButton.disabled = false;
    }
  });

  startButton.addEventListener("click", () => launchGoal(input));
  byId("controller-actions").addEventListener("click", (event) => {
    const action = event.target.dataset.ownerAction;
    if (action) submitOwnerAction(action);
  });
  byId("resume-controller").addEventListener("click", resumeController);
}

document.addEventListener("DOMContentLoaded", () => {
  configureGoalForm();
  configurePreferences();
  const now = new Date();
  byId("dispatch-date").value = [now.getFullYear(), String(now.getMonth() + 1).padStart(2, "0"), String(now.getDate()).padStart(2, "0")].join("-");
  byId("refresh-fleet").addEventListener("click", () => loadFleet());
  ["fleet-company", "fleet-type", "fleet-capacity"].forEach((id) => byId(id).addEventListener("change", () => loadFleet()));
  byId("refresh-dispatch").addEventListener("click", loadDispatch);
  Promise.allSettled([
    loadLocalActionSession(),
    loadStatus(),
    loadProjects(),
    loadKnowledge(),
    recoverCurrentJob(),
    loadFleet({ initialiseFilters: true }),
    loadDispatch(),
    loadFuel(),
  ]);
});
