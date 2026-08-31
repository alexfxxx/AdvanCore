"use strict";

const byId = (id) => document.getElementById(id);
let localActionToken = null;
let approvedPreviewGoal = null;
let activeRunId = null;
let progressStream = null;
let currentFleet = { companies: [], vehicles: [] };
let draggedFleetFieldId = null;
let selectedFleetVehicleId = null;
let fleetDrawerReturnFocus = null;
let workspacePreferences = null;
let draggedWorkspaceSegmentId = null;
let projectsExpanded = false;
let knowledgeExpanded = false;
let currentProjects = [];
let currentKnowledge = [];
const DISPLAY_PREFERENCE_KEY = "advancore.console.preferences.v1";
const FLEET_FIELD_PREFERENCE_KEY = "advancore.fleet.fields.v1";
const WORKSPACE_LAYOUT_KEY = "advancore.workspace.layout.v1";
const WORKSPACE_LAYOUT_VERSION = 1;
const FLEET_OVERVIEW_LIMIT = 8;
const SUMMARY_RECORD_LIMIT = 3;
const DISPLAY_ALLOWLIST = {
  theme: ["midnight", "light-business", "graphite"],
  shape: ["soft", "compact"],
  motion: ["full", "reduced"],
};
const FLEET_FIELD_CATALOG = Object.freeze([
  { id: "registered_owner", label: "Registered owner", visible: true },
  { id: "make_model", label: "Make / model", visible: true },
  { id: "vehicle_seating", label: "Vehicle / seating", visible: true },
  { id: "year_propellant", label: "Year / propellant", visible: true },
  { id: "parking", label: "Parking", visible: true },
  { id: "insurance", label: "Insurance", visible: true },
  { id: "road_tax", label: "Road tax", visible: true },
  { id: "coe_expiry", label: "COE expiry", visible: true },
  { id: "scheme", label: "Scheme", visible: false },
  { id: "chassis_number", label: "Chassis number", visible: false },
  { id: "engine_number", label: "Engine number", visible: false },
  { id: "original_registration_date", label: "Original registration date", visible: false },
  { id: "lifespan_expiry", label: "Lifespan expiry", visible: false },
  { id: "primary_colour", label: "Primary colour", visible: false },
  { id: "unladen_weight_kg", label: "Unladen weight", visible: false },
  { id: "maximum_laden_weight_kg", label: "Maximum laden weight", visible: false },
  { id: "finance_company", label: "Finance company", visible: true },
  { id: "original_loan_amount", label: "Original loan amount", visible: true },
  { id: "monthly_instalment", label: "Monthly instalment", visible: true },
  { id: "loan_start_date", label: "Loan start date", visible: true },
  { id: "loan_term_months", label: "Total loan term", visible: true },
  { id: "remaining_scheduled_payments", label: "Remaining scheduled payments", visible: true },
  { id: "projected_remaining_scheduled_amount", label: "Projected remaining scheduled amount", visible: true },
]);
const WORKSPACE_SIZE_CATALOG = Object.freeze({
  small: 4,
  medium: 6,
  wide: 8,
  full: 12,
});
const WORKSPACE_SEGMENT_CATALOG = Object.freeze([
  { id: "controller", label: "Owner Goal", size: "wide", visible: true },
  { id: "readiness", label: "Local Readiness", size: "small", visible: true },
  { id: "fleet", label: "Fleet", size: "wide", visible: true },
  { id: "dispatch", label: "Dispatch", size: "small", visible: true },
  { id: "fuel", label: "Fuel benchmark", size: "small", visible: true },
  { id: "projects", label: "Projects", size: "small", visible: true },
  { id: "knowledge", label: "Knowledge", size: "small", visible: true },
  { id: "voice", label: "Voice console", size: "small", visible: false },
  { id: "appearance", label: "Console appearance", size: "medium", visible: false },
  { id: "governance", label: "Governance boundary", size: "full", visible: false },
]);
let fleetFieldPreferences = defaultFleetFieldPreferences();

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

function defaultFleetFieldPreferences() {
  return {
    order: FLEET_FIELD_CATALOG.map((field) => field.id),
    visible: FLEET_FIELD_CATALOG.filter((field) => field.visible).map((field) => field.id),
  };
}

function validatedFleetFieldPreferences(raw) {
  const defaults = defaultFleetFieldPreferences();
  if (!raw || typeof raw !== "object" || !Array.isArray(raw.order) || !Array.isArray(raw.visible)) return defaults;
  const approved = new Set(defaults.order);
  const orderIsSafe = raw.order.every((id) => typeof id === "string" && approved.has(id));
  const visibleIsSafe = raw.visible.every((id) => typeof id === "string" && approved.has(id));
  if (!orderIsSafe || !visibleIsSafe || new Set(raw.order).size !== raw.order.length || new Set(raw.visible).size !== raw.visible.length) return defaults;
  const order = [...raw.order];
  defaults.order.forEach((id) => { if (!order.includes(id)) order.push(id); });
  return { order, visible: [...raw.visible] };
}

function readFleetFieldPreferences() {
  try {
    return validatedFleetFieldPreferences(JSON.parse(localStorage.getItem(FLEET_FIELD_PREFERENCE_KEY)));
  } catch (_error) {
    return defaultFleetFieldPreferences();
  }
}

function saveFleetFieldPreferences(preferences) {
  fleetFieldPreferences = validatedFleetFieldPreferences(preferences);
  try {
    localStorage.setItem(FLEET_FIELD_PREFERENCE_KEY, JSON.stringify(fleetFieldPreferences));
  } catch (_error) {
    // A blocked or full browser store must not stop the read-only Fleet view.
  }
  renderFleetFieldControls();
  renderFleetOverview();
  if (selectedFleetVehicleId !== null) renderFleetDrawer(selectedFleetVehicleId);
}

function fleetFieldValue(fieldId, vehicle, companies) {
  const owner = companies.find((item) => item.id === vehicle.registered_owner_id);
  const values = {
    registered_owner: owner?.name || "Not recorded",
    make_model: vehicle.make_model || "Not recorded",
    vehicle_seating: [vehicle.vehicle_type, vehicle.passenger_capacity ? `${vehicle.passenger_capacity} seats` : null].filter(Boolean).join(" · ") || "Not recorded",
    year_propellant: [vehicle.manufacture_year, vehicle.propellant].filter(Boolean).join(" · ") || "Not recorded",
    parking: [vehicle.parking_provider, vehicle.parking_location, formatMoney(vehicle.parking_monthly_cost)].filter((item) => item && item !== "Not recorded").join(" · ") || "Not recorded",
    insurance: [vehicle.insurance_provider, formatMoney(vehicle.insurance_annual_amount)].filter((item) => item && item !== "Not recorded").join(" · ") || "Not recorded",
    road_tax: vehicle.road_tax_amount === null || vehicle.road_tax_amount === undefined ? "Not recorded" : `${formatMoney(vehicle.road_tax_amount)} / ${vehicle.road_tax_period_months} months`,
    coe_expiry: vehicle.coe_expiry || "Not recorded",
    scheme: vehicle.scheme || "Not recorded",
    chassis_number: vehicle.chassis_number || "Not recorded",
    engine_number: vehicle.engine_number || "Not recorded",
    original_registration_date: vehicle.original_registration_date || "Not recorded",
    lifespan_expiry: vehicle.lifespan_expiry || "Not recorded",
    primary_colour: vehicle.primary_colour || "Not recorded",
    unladen_weight_kg: vehicle.unladen_weight_kg === null || vehicle.unladen_weight_kg === undefined ? "Not recorded" : `${vehicle.unladen_weight_kg} kg`,
    maximum_laden_weight_kg: vehicle.maximum_laden_weight_kg === null || vehicle.maximum_laden_weight_kg === undefined ? "Not recorded" : `${vehicle.maximum_laden_weight_kg} kg`,
    finance_company: vehicle.finance_company || "Not recorded",
    original_loan_amount: formatMoney(vehicle.original_loan_amount),
    monthly_instalment: formatMoney(vehicle.monthly_instalment),
    loan_start_date: vehicle.loan_start_date || "Not recorded",
    loan_term_months: vehicle.loan_term_months === null || vehicle.loan_term_months === undefined ? "Not recorded" : `${vehicle.loan_term_months} months`,
    remaining_scheduled_payments: vehicle.remaining_scheduled_payments === null || vehicle.remaining_scheduled_payments === undefined ? "Not recorded" : String(vehicle.remaining_scheduled_payments),
    projected_remaining_scheduled_amount: formatMoney(vehicle.projected_remaining_scheduled_amount),
  };
  return values[fieldId] ?? "Not recorded";
}

function filteredFleetVehicles() {
  const query = (byId("fleet-search")?.value || "").trim().toLocaleLowerCase();
  if (!query) return currentFleet.vehicles;
  return currentFleet.vehicles.filter((vehicle) => (
    `${vehicle.registration_number || ""} ${vehicle.make_model || ""}`
      .toLocaleLowerCase()
      .includes(query)
  ));
}

function fleetCompactRow(vehicle, companies) {
  const owner = companies.find((item) => item.id === vehicle.registered_owner_id);
  const row = document.createElement("button");
  row.type = "button";
  row.className = "fleet-compact-row";
  row.setAttribute("role", "listitem");
  row.setAttribute("aria-label", `Open ${vehicle.registration_number} details`);
  const details = [
    ["Plate", vehicle.registration_number],
    ["Model", vehicle.make_model || "Not recorded"],
    ["Owner", owner?.name || "Not recorded"],
    ["Type", [vehicle.vehicle_type, vehicle.passenger_capacity ? `${vehicle.passenger_capacity} seats` : null].filter(Boolean).join(" · ") || "Not recorded"],
  ];
  details.forEach(([label, value], index) => {
    const cell = document.createElement("span");
    cell.className = index === 0 ? "fleet-primary-cell" : "fleet-row-cell";
    const term = document.createElement("small");
    term.textContent = label;
    const result = document.createElement("strong");
    result.textContent = value;
    cell.append(term, result);
    row.append(cell);
  });
  const status = document.createElement("span");
  status.className = "record-status";
  status.textContent = vehicle.status || "Recorded";
  row.append(status);
  row.addEventListener("click", () => openFleetDrawer(vehicle.id, row));
  return row;
}

function renderFleetOverview() {
  const vehicles = filteredFleetVehicles();
  const container = byId("fleet-list");
  if (!container) return;
  container.replaceChildren();
  setText("fleet-match-count", vehicles.length);
  setText("fleet-owner-count", new Set(vehicles.map((vehicle) => vehicle.registered_owner_id).filter(Boolean)).size);
  const busCount = vehicles.filter((vehicle) => String(vehicle.vehicle_type).toLocaleLowerCase() === "bus").length;
  setText("fleet-bus-count", busCount);
  setText("fleet-other-count", vehicles.length - busCount);
  if (!vehicles.length) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = "No vehicles match these filters.";
    container.append(empty);
    setText("fleet-summary", "No vehicle records match the current filters.");
    return;
  }
  vehicles.slice(0, FLEET_OVERVIEW_LIMIT).forEach((vehicle) => {
    container.append(fleetCompactRow(vehicle, currentFleet.companies));
  });
  const shown = Math.min(vehicles.length, FLEET_OVERVIEW_LIMIT);
  setText("fleet-summary", `${vehicles.length} vehicle${vehicles.length === 1 ? "" : "s"} match. Showing ${shown}; select one for full details. No sample records are generated.`);
}

function renderFleetUnavailable(message) {
  currentFleet = { companies: [], vehicles: [] };
  closeFleetDrawer();
  setText("fleet-match-count", "—");
  setText("fleet-owner-count", "—");
  setText("fleet-bus-count", "—");
  setText("fleet-other-count", "—");
  setText("fleet-summary", message);
  const container = byId("fleet-list");
  container.replaceChildren();
  const unavailable = document.createElement("p");
  unavailable.className = "empty-state";
  unavailable.textContent = "Fleet is unavailable. Existing records have not been changed.";
  container.append(unavailable);
}

function renderFleetDrawer(vehicleId) {
  const vehicle = currentFleet.vehicles.find((item) => String(item.id) === String(vehicleId));
  if (!vehicle) {
    closeFleetDrawer();
    return;
  }
  selectedFleetVehicleId = vehicle.id;
  setText("fleet-drawer-title", vehicle.registration_number);
  setText("fleet-drawer-status", vehicle.status || "Recorded");
  const grid = byId("fleet-drawer-details");
  grid.replaceChildren();
  const visible = new Set(fleetFieldPreferences.visible);
  fleetFieldPreferences.order.filter((id) => visible.has(id)).forEach((id) => {
    const field = FLEET_FIELD_CATALOG.find((item) => item.id === id);
    if (field) appendDetail(grid, field.label, fleetFieldValue(id, vehicle, currentFleet.companies));
  });
}

function openFleetDrawer(vehicleId, returnFocus = null) {
  fleetDrawerReturnFocus = returnFocus || document.activeElement;
  renderFleetDrawer(vehicleId);
  byId("fleet-drawer").hidden = false;
  byId("fleet-drawer-backdrop").hidden = false;
  document.body.classList.add("drawer-open");
  byId("close-fleet-drawer").focus();
}

function closeFleetDrawer() {
  const drawer = byId("fleet-drawer");
  const backdrop = byId("fleet-drawer-backdrop");
  if (drawer) drawer.hidden = true;
  if (backdrop) backdrop.hidden = true;
  document.body.classList.remove("drawer-open");
  selectedFleetVehicleId = null;
  if (fleetDrawerReturnFocus?.isConnected) fleetDrawerReturnFocus.focus();
  fleetDrawerReturnFocus = null;
}

function keepFocusInFleetDrawer(event) {
  if (event.key !== "Tab" || byId("fleet-drawer")?.hidden) return;
  const focusable = [...byId("fleet-drawer").querySelectorAll("button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])")]
    .filter((element) => !element.disabled && !element.hidden);
  if (!focusable.length) return;
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

function renderFleetCards() {
  renderFleetOverview();
}

function moveFleetField(fieldId, offset) {
  const order = [...fleetFieldPreferences.order];
  const current = order.indexOf(fieldId);
  const target = Math.max(0, Math.min(order.length - 1, current + offset));
  if (current < 0 || current === target) return;
  order.splice(current, 1);
  order.splice(target, 0, fieldId);
  saveFleetFieldPreferences({ ...fleetFieldPreferences, order });
}

function reorderedFleetFieldIds(currentOrder, fieldId, targetId) {
  const order = [...currentOrder];
  const source = order.indexOf(fieldId);
  const target = order.indexOf(targetId);
  if (source < 0 || target < 0 || source === target) return order;
  order.splice(source, 1);
  // The original target index deliberately means "after" while moving down
  // and "before" while moving up, so the final row is a valid drop target.
  order.splice(target, 0, fieldId);
  return order;
}

function placeFleetFieldAtDrop(fieldId, targetId) {
  const order = reorderedFleetFieldIds(
    fleetFieldPreferences.order,
    fieldId,
    targetId,
  );
  if (order.every((id, index) => id === fleetFieldPreferences.order[index])) return;
  saveFleetFieldPreferences({ ...fleetFieldPreferences, order });
}

function renderFleetFieldControls() {
  const list = byId("fleet-field-layout");
  if (!list) return;
  list.replaceChildren();
  const visible = new Set(fleetFieldPreferences.visible);
  fleetFieldPreferences.order.forEach((fieldId, index) => {
    const field = FLEET_FIELD_CATALOG.find((item) => item.id === fieldId);
    if (!field) return;
    const row = document.createElement("li");
    row.className = "fleet-field-row";
    row.draggable = true;
    row.dataset.fieldId = field.id;
    row.addEventListener("dragstart", () => { draggedFleetFieldId = field.id; row.classList.add("dragging"); });
    row.addEventListener("dragend", () => { draggedFleetFieldId = null; row.classList.remove("dragging"); });
    row.addEventListener("dragover", (event) => event.preventDefault());
    row.addEventListener("drop", (event) => { event.preventDefault(); placeFleetFieldAtDrop(draggedFleetFieldId, field.id); });

    const toggleLabel = document.createElement("label");
    const toggle = document.createElement("input");
    toggle.type = "checkbox";
    toggle.checked = visible.has(field.id);
    toggle.addEventListener("change", () => {
      const next = new Set(fleetFieldPreferences.visible);
      if (toggle.checked) next.add(field.id); else next.delete(field.id);
      saveFleetFieldPreferences({ ...fleetFieldPreferences, visible: [...next] });
    });
    const label = document.createElement("span");
    label.textContent = field.label;
    toggleLabel.append(toggle, label);

    const controls = document.createElement("span");
    controls.className = "fleet-field-move-controls";
    const up = document.createElement("button");
    up.type = "button";
    up.textContent = "↑";
    up.title = `Move ${field.label} up`;
    up.setAttribute("aria-label", up.title);
    up.disabled = index === 0;
    up.addEventListener("click", () => moveFleetField(field.id, -1));
    const down = document.createElement("button");
    down.type = "button";
    down.textContent = "↓";
    down.title = `Move ${field.label} down`;
    down.setAttribute("aria-label", down.title);
    down.disabled = index === fleetFieldPreferences.order.length - 1;
    down.addEventListener("click", () => moveFleetField(field.id, 1));
    controls.append(up, down);
    row.append(toggleLabel, controls);
    list.append(row);
  });
}

function configureFleetFieldPreferences() {
  fleetFieldPreferences = readFleetFieldPreferences();
  renderFleetFieldControls();
  byId("reset-fleet-fields").addEventListener("click", () => saveFleetFieldPreferences(defaultFleetFieldPreferences()));
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
    currentFleet = fleet;
    if (selectedFleetVehicleId !== null) {
      if (fleet.vehicles.some((vehicle) => String(vehicle.id) === String(selectedFleetVehicleId))) {
        renderFleetDrawer(selectedFleetVehicleId);
      } else {
        closeFleetDrawer();
      }
    }
    renderFleetOverview();
  } catch (error) {
    renderFleetUnavailable(error.message);
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
    const actionableRows = board.rows.filter((row) => row.conflicts.length).slice(0, SUMMARY_RECORD_LIMIT);
    renderRecords("dispatch-list", actionableRows, dispatchCard, "No dispatch conflicts are recorded for this date.");
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

function defaultWorkspacePreferences() {
  return {
    version: WORKSPACE_LAYOUT_VERSION,
    segments: WORKSPACE_SEGMENT_CATALOG.map((segment) => ({
      id: segment.id,
      visible: segment.visible,
      size: segment.size,
    })),
  };
}

function validatedWorkspaceLayout(raw) {
  const defaults = defaultWorkspacePreferences();
  if (!raw || typeof raw !== "object" || raw.version !== WORKSPACE_LAYOUT_VERSION || !Array.isArray(raw.segments)) return defaults;
  if (raw.segments.length !== WORKSPACE_SEGMENT_CATALOG.length) return defaults;
  const approvedIds = new Set(WORKSPACE_SEGMENT_CATALOG.map((segment) => segment.id));
  const seen = new Set();
  const segments = [];
  for (const candidate of raw.segments) {
    if (!candidate || typeof candidate !== "object") return defaults;
    if (typeof candidate.id !== "string" || !approvedIds.has(candidate.id) || seen.has(candidate.id)) return defaults;
    if (typeof candidate.visible !== "boolean" || !Object.hasOwn(WORKSPACE_SIZE_CATALOG, candidate.size)) return defaults;
    seen.add(candidate.id);
    segments.push({ id: candidate.id, visible: candidate.visible, size: candidate.size });
  }
  if (seen.size !== approvedIds.size || !segments.some((segment) => segment.visible)) return defaults;
  return { version: WORKSPACE_LAYOUT_VERSION, segments };
}

function reorderedWorkspaceSegmentIds(currentOrder, segmentId, targetId) {
  const order = [...currentOrder];
  const source = order.indexOf(segmentId);
  const target = order.indexOf(targetId);
  if (source < 0 || target < 0 || source === target) return order;
  order.splice(source, 1);
  order.splice(target, 0, segmentId);
  return order;
}

function readWorkspacePreferences() {
  try {
    return validatedWorkspaceLayout(JSON.parse(localStorage.getItem(WORKSPACE_LAYOUT_KEY)));
  } catch (_error) {
    return defaultWorkspacePreferences();
  }
}

function persistWorkspacePreferences(preferences) {
  workspacePreferences = validatedWorkspaceLayout(preferences);
  let stored = true;
  try {
    localStorage.setItem(WORKSPACE_LAYOUT_KEY, JSON.stringify(workspacePreferences));
  } catch (_error) {
    stored = false;
  }
  applyWorkspacePreferences();
  setText(
    "workspace-layout-status",
    stored ? "Layout saved only in this browser." : "Layout changed for this page, but browser storage is unavailable.",
  );
}

function workspaceSegmentLabel(segmentId) {
  return WORKSPACE_SEGMENT_CATALOG.find((segment) => segment.id === segmentId)?.label || segmentId;
}

function applyWorkspacePreferences() {
  const workspace = byId("workspace");
  if (!workspace || !workspacePreferences) return;
  workspacePreferences.segments.forEach((preference) => {
    const segment = workspace.querySelector(`[data-segment-id="${preference.id}"]`);
    if (!segment) return;
    segment.dataset.segmentSize = preference.size;
    segment.hidden = !preference.visible;
    segment.draggable = document.body.classList.contains("workspace-editing");
    workspace.append(segment);
  });
  updateMobileSegmentSelector();
  renderWorkspaceEditor();
}

function workspaceSegmentsWithUpdate(segments, segmentId, changes) {
  return segments.map((segment) => (
    segment.id === segmentId ? { ...segment, ...changes } : { ...segment }
  ));
}

function updateWorkspaceSegment(segmentId, changes) {
  const next = workspaceSegmentsWithUpdate(workspacePreferences.segments, segmentId, changes);
  persistWorkspacePreferences({ version: WORKSPACE_LAYOUT_VERSION, segments: next });
}

function moveWorkspaceSegment(segmentId, offset) {
  const segments = workspacePreferences.segments.map((segment) => ({ ...segment }));
  const source = segments.findIndex((segment) => segment.id === segmentId);
  const target = Math.max(0, Math.min(segments.length - 1, source + offset));
  if (source < 0 || source === target) return;
  const [moved] = segments.splice(source, 1);
  segments.splice(target, 0, moved);
  persistWorkspacePreferences({ version: WORKSPACE_LAYOUT_VERSION, segments });
}

function placeWorkspaceSegmentAtDrop(segmentId, targetId) {
  const current = workspacePreferences.segments;
  const order = reorderedWorkspaceSegmentIds(current.map((segment) => segment.id), segmentId, targetId);
  if (order.every((id, index) => id === current[index].id)) return;
  const bySegmentId = new Map(current.map((segment) => [segment.id, segment]));
  persistWorkspacePreferences({
    version: WORKSPACE_LAYOUT_VERSION,
    segments: order.map((id) => ({ ...bySegmentId.get(id) })),
  });
}

function replacedWorkspaceSegments(currentSegments, segmentId, replacementId) {
  const segments = currentSegments.map((segment) => ({ ...segment }));
  if (!replacementId || segmentId === replacementId) return segments;
  const source = segments.findIndex((segment) => segment.id === segmentId);
  const replacement = segments.findIndex((segment) => segment.id === replacementId);
  if (source < 0 || replacement < 0 || segments[replacement].visible) return segments;
  segments[source].visible = false;
  segments[replacement].visible = true;
  [segments[source], segments[replacement]] = [segments[replacement], segments[source]];
  return segments;
}

function replaceWorkspaceSegment(segmentId, replacementId) {
  const segments = replacedWorkspaceSegments(workspacePreferences.segments, segmentId, replacementId);
  persistWorkspacePreferences({ version: WORKSPACE_LAYOUT_VERSION, segments });
}

function renderWorkspaceEditor() {
  const list = byId("workspace-layout-list");
  if (!list || !workspacePreferences) return;
  list.replaceChildren();
  const hiddenSegments = workspacePreferences.segments.filter((segment) => !segment.visible);
  workspacePreferences.segments.forEach((segment, index) => {
    const row = document.createElement("li");
    row.className = "workspace-layout-row";
    row.draggable = true;
    row.dataset.segmentId = segment.id;
    row.addEventListener("dragstart", () => { draggedWorkspaceSegmentId = segment.id; row.classList.add("dragging"); });
    row.addEventListener("dragend", () => { draggedWorkspaceSegmentId = null; row.classList.remove("dragging"); });
    row.addEventListener("dragover", (event) => event.preventDefault());
    row.addEventListener("drop", (event) => { event.preventDefault(); placeWorkspaceSegmentAtDrop(draggedWorkspaceSegmentId, segment.id); });

    const visibleLabel = document.createElement("label");
    visibleLabel.className = "workspace-visible-toggle";
    const visible = document.createElement("input");
    visible.type = "checkbox";
    visible.checked = segment.visible;
    visible.addEventListener("change", () => updateWorkspaceSegment(segment.id, { visible: visible.checked }));
    const name = document.createElement("strong");
    name.textContent = workspaceSegmentLabel(segment.id);
    visibleLabel.append(visible, name);

    const size = document.createElement("select");
    size.setAttribute("aria-label", `${workspaceSegmentLabel(segment.id)} width`);
    Object.keys(WORKSPACE_SIZE_CATALOG).forEach((value) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = value[0].toUpperCase() + value.slice(1);
      option.selected = value === segment.size;
      size.append(option);
    });
    size.addEventListener("change", () => updateWorkspaceSegment(segment.id, { size: size.value }));

    const replace = document.createElement("select");
    replace.setAttribute("aria-label", `Replace ${workspaceSegmentLabel(segment.id)}`);
    const keep = document.createElement("option");
    keep.value = "";
    keep.textContent = "Replace with…";
    replace.append(keep);
    hiddenSegments.filter((candidate) => candidate.id !== segment.id).forEach((candidate) => {
      const option = document.createElement("option");
      option.value = candidate.id;
      option.textContent = workspaceSegmentLabel(candidate.id);
      replace.append(option);
    });
    replace.disabled = !segment.visible || replace.options.length === 1;
    replace.addEventListener("change", () => replaceWorkspaceSegment(segment.id, replace.value));

    const controls = document.createElement("span");
    controls.className = "workspace-move-controls";
    [-1, 1].forEach((offset) => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = offset < 0 ? "↑" : "↓";
      button.title = `Move ${workspaceSegmentLabel(segment.id)} ${offset < 0 ? "up" : "down"}`;
      button.setAttribute("aria-label", button.title);
      button.disabled = offset < 0 ? index === 0 : index === workspacePreferences.segments.length - 1;
      button.addEventListener("click", () => moveWorkspaceSegment(segment.id, offset));
      controls.append(button);
    });
    row.append(visibleLabel, size, replace, controls);
    list.append(row);
  });
}

function updateMobileSegmentSelector() {
  const select = byId("mobile-segment-select");
  if (!select || !workspacePreferences) return;
  const previous = select.value;
  const visible = workspacePreferences.segments.filter((segment) => segment.visible);
  select.replaceChildren();
  visible.forEach((segment) => {
    const option = document.createElement("option");
    option.value = segment.id;
    option.textContent = workspaceSegmentLabel(segment.id);
    select.append(option);
  });
  select.value = visible.some((segment) => segment.id === previous) ? previous : visible[0]?.id || "";
  document.querySelectorAll(".workspace-segment").forEach((segment) => {
    segment.dataset.mobileActive = String(segment.dataset.segmentId === select.value);
  });
}

function setWorkspaceEditing(editing) {
  document.body.classList.toggle("workspace-editing", editing);
  byId("workspace-editor").hidden = !editing;
  byId("edit-workspace").setAttribute("aria-expanded", String(editing));
  document.querySelectorAll(".workspace-segment").forEach((segment) => { segment.draggable = editing; });
  if (editing) byId("workspace-editor").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function resetWorkspace({ resetDisplay = false } = {}) {
  let storageReset = true;
  try {
    localStorage.removeItem(WORKSPACE_LAYOUT_KEY);
    if (resetDisplay) {
      localStorage.removeItem(DISPLAY_PREFERENCE_KEY);
      localStorage.removeItem(FLEET_FIELD_PREFERENCE_KEY);
    }
  } catch (_error) {
    storageReset = false;
  }
  workspacePreferences = defaultWorkspacePreferences();
  if (resetDisplay) {
    applyPreferences(null);
    fleetFieldPreferences = defaultFleetFieldPreferences();
    renderFleetFieldControls();
    renderFleetOverview();
  }
  applyWorkspacePreferences();
  const successLabel = resetDisplay ? "Display and layout reset." : "Workspace reset.";
  setText("workspace-layout-status", storageReset ? successLabel : `${successLabel} Browser storage remains unavailable, so refresh may restore earlier choices.`);
}

function configureWorkspace() {
  workspacePreferences = readWorkspacePreferences();
  const workspace = byId("workspace");
  workspace.addEventListener("dragstart", (event) => {
    const segment = event.target.closest(".workspace-segment");
    if (!document.body.classList.contains("workspace-editing") || !segment) return;
    draggedWorkspaceSegmentId = segment.dataset.segmentId;
    segment.classList.add("dragging");
  });
  workspace.addEventListener("dragend", (event) => {
    event.target.closest(".workspace-segment")?.classList.remove("dragging");
    draggedWorkspaceSegmentId = null;
  });
  workspace.addEventListener("dragover", (event) => {
    if (document.body.classList.contains("workspace-editing") && event.target.closest(".workspace-segment")) event.preventDefault();
  });
  workspace.addEventListener("drop", (event) => {
    const target = event.target.closest(".workspace-segment");
    if (target && draggedWorkspaceSegmentId) placeWorkspaceSegmentAtDrop(draggedWorkspaceSegmentId, target.dataset.segmentId);
  });
  byId("edit-workspace").addEventListener("click", () => setWorkspaceEditing(!document.body.classList.contains("workspace-editing")));
  byId("close-workspace-editor").addEventListener("click", () => setWorkspaceEditing(false));
  byId("reset-workspace").addEventListener("click", () => resetWorkspace());
  byId("reset-display-layout").addEventListener("click", () => resetWorkspace({ resetDisplay: true }));
  byId("mobile-segment-select").addEventListener("change", updateMobileSegmentSelector);
  applyWorkspacePreferences();
  setText("workspace-layout-status", "Layout loaded from this browser.");
}

function updateMotionState() {
  const savedReduced = document.documentElement.dataset.motion === "reduced";
  const systemReduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches || false;
  const label = savedReduced
    ? "Motion reduced by console setting"
    : systemReduced ? "Motion reduced by browser/OS" : "Full motion enabled";
  setText("motion-state", label);
  setText("appearance-motion-state", label);
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
  try {
    localStorage.setItem(DISPLAY_PREFERENCE_KEY, JSON.stringify(safe));
  } catch (_error) {
    // Display preferences remain usable for this page when storage is blocked.
  }
  updateMotionState();
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
    currentProjects = await requestJson("/api/projects");
    renderProjectSummary();
  } catch (error) {
    renderRecords("projects-list", [], recordRow, error.message);
  }
}

function recentActiveRecords(records) {
  const inactiveStatuses = new Set(["archived", "inactive", "replaced", "superseded"]);
  return [...records].sort((left, right) => {
    const leftInactive = inactiveStatuses.has(String(left.status || "").toLocaleLowerCase());
    const rightInactive = inactiveStatuses.has(String(right.status || "").toLocaleLowerCase());
    if (leftInactive !== rightInactive) return leftInactive ? 1 : -1;
    const leftDate = String(left.updated_at || left.created_at || "");
    const rightDate = String(right.updated_at || right.created_at || "");
    return rightDate.localeCompare(leftDate);
  });
}

function renderProjectSummary() {
  const ordered = recentActiveRecords(currentProjects);
  const records = projectsExpanded ? ordered : ordered.slice(0, SUMMARY_RECORD_LIMIT);
    renderRecords(
      "projects-list",
      records,
      (project) => recordRow(project.name, project.description || "No description recorded", project.status),
      "No projects recorded.",
    );
  const toggle = byId("toggle-projects");
  toggle.hidden = currentProjects.length <= SUMMARY_RECORD_LIMIT;
  toggle.textContent = projectsExpanded ? "Show summary" : `View all ${currentProjects.length} projects`;
}

async function loadKnowledge() {
  try {
    currentKnowledge = await requestJson("/api/knowledge");
    renderKnowledgeSummary();
  } catch (error) {
    renderRecords("knowledge-list", [], recordRow, error.message);
  }
}

function renderKnowledgeSummary() {
  const ordered = recentActiveRecords(currentKnowledge);
  const records = knowledgeExpanded ? ordered : ordered.slice(0, SUMMARY_RECORD_LIMIT);
    renderRecords(
      "knowledge-list",
      records,
      (item) => recordRow(item.title, `Project ${item.project_id ?? "not linked"}`, item.status),
      "No Knowledge items recorded.",
    );
  const toggle = byId("toggle-knowledge");
  toggle.hidden = currentKnowledge.length <= SUMMARY_RECORD_LIMIT;
  toggle.textContent = knowledgeExpanded ? "Show summary" : `View all ${currentKnowledge.length} Knowledge items`;
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
  configureWorkspace();
  configureFleetFieldPreferences();
  const motionQuery = window.matchMedia?.("(prefers-reduced-motion: reduce)");
  motionQuery?.addEventListener?.("change", updateMotionState);
  const now = new Date();
  byId("dispatch-date").value = [now.getFullYear(), String(now.getMonth() + 1).padStart(2, "0"), String(now.getDate()).padStart(2, "0")].join("-");
  byId("refresh-fleet").addEventListener("click", () => loadFleet());
  ["fleet-company", "fleet-type", "fleet-capacity"].forEach((id) => byId(id).addEventListener("change", () => loadFleet()));
  byId("fleet-search").addEventListener("input", renderFleetOverview);
  byId("close-fleet-drawer").addEventListener("click", closeFleetDrawer);
  byId("fleet-drawer-backdrop").addEventListener("click", closeFleetDrawer);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !byId("fleet-drawer").hidden) closeFleetDrawer();
    else keepFocusInFleetDrawer(event);
  });
  byId("toggle-projects").addEventListener("click", () => {
    projectsExpanded = !projectsExpanded;
    renderProjectSummary();
  });
  byId("toggle-knowledge").addEventListener("click", () => {
    knowledgeExpanded = !knowledgeExpanded;
    renderKnowledgeSummary();
  });
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

if (typeof window !== "undefined") {
  window.AdvanCoreConsole = Object.freeze({
    refreshProjects: loadProjects,
    refreshKnowledge: loadKnowledge,
    refreshFleet: () => loadFleet({ initialiseFilters: true }),
    refreshDispatch: loadDispatch,
  });
}
