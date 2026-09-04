"use strict";

(() => {
  const byId = (id) => document.getElementById(id);
  const manager = byId("record-manager");
  const backdrop = byId("record-manager-backdrop");
  const content = byId("record-manager-content");
  const statusLine = byId("record-manager-status");
  const confirmation = byId("edit-confirmation");
  const summaryList = byId("edit-confirmation-summary");
  let activeTab = "dashboard";
  let pendingConfirmation = null;

  const element = (tag, options = {}, children = []) => {
    const node = document.createElement(tag);
    Object.entries(options).forEach(([key, value]) => {
      if (key === "className") node.className = value;
      else if (key === "text") node.textContent = value;
      else if (key === "dataset") Object.assign(node.dataset, value);
      else if (key === "checked") node.checked = Boolean(value);
      else if (key === "value") node.value = value ?? "";
      else if (value !== undefined && value !== null) node.setAttribute(key, value);
    });
    children.filter(Boolean).forEach((child) => node.append(child));
    return node;
  };

  const button = (label, className = "secondary-action-button") =>
    element("button", { type: "button", className, text: label });

  const setStatus = (message, tone = "") => {
    statusLine.textContent = message;
    statusLine.dataset.tone = tone;
  };

  const displayValue = (value) => {
    if (value === null || value === undefined || value === "") return "Not recorded";
    return String(value).replaceAll("_", " ");
  };

  const todayValue = () => {
    const now = new Date();
    return [
      now.getFullYear(),
      String(now.getMonth() + 1).padStart(2, "0"),
      String(now.getDate()).padStart(2, "0"),
    ].join("-");
  };

  const indexedById = (records) => new Map(records.map((record) => [record.id, record]));

  const sha256Hex = async (value) => {
    const bytes = new TextEncoder().encode(value);
    const digest = await crypto.subtle.digest("SHA-256", bytes);
    return Array.from(new Uint8Array(digest), (byte) =>
      byte.toString(16).padStart(2, "0")
    ).join("");
  };

  const field = (label, name, options = {}) => {
    const wrapper = element("label", { className: options.wide ? "manager-field manager-field-wide" : "manager-field" });
    wrapper.append(element("span", { text: label }));
    let input;
    if (options.type === "textarea") {
      input = element("textarea", { name, rows: options.rows || "4", maxlength: options.maxlength || "20000" });
    } else if (options.options) {
      input = element("select", { name });
      options.options.forEach(([value, text]) => input.append(element("option", { value, text })));
    } else {
      input = element("input", {
        name,
        type: options.type || "text",
        maxlength: options.maxlength,
        min: options.min,
        max: options.max,
        step: options.step,
      });
    }
    if (options.required) input.required = true;
    if (options.value !== undefined && options.value !== null) input.value = options.value;
    wrapper.append(input);
    return wrapper;
  };

  const formSection = (title, description = "") => {
    const section = element("section", { className: "manager-section" });
    section.append(element("h3", { text: title }));
    if (description) section.append(element("p", { className: "micro-copy left-copy", text: description }));
    return section;
  };

  const toPayload = (form, numericFields = []) => {
    const payload = {};
    new FormData(form).forEach((rawValue, key) => {
      const value = typeof rawValue === "string" ? rawValue.trim() : rawValue;
      if (value === "") payload[key] = null;
      else if (numericFields.includes(key)) payload[key] = Number(value);
      else payload[key] = value;
    });
    return payload;
  };

  const readJson = async (url) => {
    const response = await fetch(url, { headers: { Accept: "application/json" } });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || `Request failed (${response.status}).`);
    return data;
  };

  const actionToken = async () => {
    const session = await readJson("/api/session");
    if (!session.action_token) throw new Error("Local action session is unavailable.");
    return session.action_token;
  };

  const postJson = async (url, payload) => {
    const token = await actionToken();
    const response = await fetch(url, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-AdvanCore-Action-Token": token,
      },
      body: JSON.stringify({ ...payload, confirmed: true }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = Array.isArray(data.detail)
        ? data.detail.map((item) => item.msg).join("; ")
        : data.detail;
      throw new Error(detail || `Change failed (${response.status}).`);
    }
    return data;
  };

  const confirmChange = (message, summary) => new Promise((resolve) => {
    pendingConfirmation = resolve;
    byId("edit-confirmation-message").textContent = message;
    summaryList.replaceChildren(...summary.map(([label, value]) =>
      element("li", {}, [
        element("strong", { text: `${label}: ` }),
        document.createTextNode(displayValue(value)),
      ])
    ));
    confirmation.showModal();
    byId("confirm-edit-action").focus();
  });

  const resolveConfirmation = (accepted) => {
    if (confirmation.open) confirmation.close();
    const resolve = pendingConfirmation;
    pendingConfirmation = null;
    if (resolve) resolve(accepted);
  };

  const perform = async ({ message, summary, url, payload, success }) => {
    if (!(await confirmChange(message, summary))) return;
    const confirmButton = byId("confirm-edit-action");
    confirmButton.disabled = true;
    setStatus("Saving confirmed change…");
    try {
      await postJson(url, payload);
      setStatus(success, "success");
      await refreshPrimarySummaries();
      await renderActiveTab();
    } catch (error) {
      setStatus(error.message, "error");
    } finally {
      confirmButton.disabled = false;
    }
  };

  const refreshPrimarySummaries = async () => {
    const api = window.AdvanCoreConsole;
    if (!api) return;
    await Promise.allSettled([
      api.refreshProjects(), api.refreshKnowledge(), api.refreshFleet(), api.refreshDispatch(),
      api.refreshFuel(),
    ]);
  };

  const recordCard = (title, meta, actions = []) => {
    const card = element("article", { className: "manager-record" });
    const heading = element("div", { className: "manager-record-heading" }, [
      element("h4", { text: title }),
      element("span", { className: "record-status", text: meta }),
    ]);
    card.append(heading);
    card.append(element("div", {
      className: "manager-record-actions",
      hidden: actions.length ? null : "",
    }, actions));
    return card;
  };

  const empty = (message) => element("p", { className: "manager-empty", text: message });

  const money = (value, currency = "SGD") => `${currency} ${Number(value || 0).toLocaleString("en-SG", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

  const summaryMetric = (label, value, note = "") => element("article", { className: "operations-metric" }, [
    element("span", { text: label }),
    element("strong", { text: value }),
    note ? element("small", { text: note }) : null,
  ]);

  async function renderDashboard() {
    const [customers, fleet, drivers, financialEntries] = await Promise.all([
      readJson("/api/customers"), readJson("/api/fleet"), readJson("/api/drivers"), readJson("/api/financial-entries"),
    ]);
    const serviceResults = await Promise.allSettled(customers.map((customer) =>
      readJson(`/api/customers/${customer.id}/recurring-services`)
    ));
    const services = serviceResults.flatMap((result) => result.status === "fulfilled" ? result.value : []);
    const activeServices = services.filter((service) => service.status === "active");
    const monthlyIncome = activeServices.reduce((sum, service) => sum + Number(service.monthly_amount || 0), 0);
    const section = formSection("Dashboard", "A live summary of records stored on this laptop.");
    section.append(element("div", { className: "operations-metrics" }, [
      summaryMetric("Active customers", String(customers.filter((record) => record.status === "active").length), `${customers.length} total`),
      summaryMetric("Active routes", String(activeServices.length), money(monthlyIncome) + " monthly"),
      summaryMetric("Active drivers", String(drivers.filter((record) => record.status === "active").length), `${drivers.length} total`),
      summaryMetric("Fleet vehicles", String(fleet.length)),
      summaryMetric("Financial entries", String(financialEntries.length), "Recorded transactions"),
    ]));
    content.replaceChildren(section);
  }

  async function renderRouteWorkspace() {
    const customers = await readJson("/api/customers");
    const section = formSection("Routes", "Choose a customer to view and maintain all recurring routes and monthly values.");
    const selector = field("Customer", "customer_id", {
      options: [["", "Choose customer…"], ...customers.map((customer) => [String(customer.id), customer.name])],
    });
    const open = button("View customer routes", "primary-button");
    open.disabled = true;
    selector.querySelector("select").addEventListener("change", (event) => { open.disabled = !event.target.value; });
    open.addEventListener("click", () => {
      const customer = customers.find((record) => String(record.id) === selector.querySelector("select").value);
      if (customer) renderCustomerProfile(customer);
    });
    section.append(element("div", { className: "route-customer-picker" }, [selector, open]));
    const rows = element("div", { className: "manager-record-list" });
    const results = await Promise.all(customers.map(async (customer) => ({
      customer,
      services: await readJson(`/api/customers/${customer.id}/recurring-services`),
    })));
    results.forEach(({ customer, services }) => {
      const active = services.filter((service) => service.status === "active");
      const total = active.reduce((sum, service) => sum + Number(service.monthly_amount || 0), 0);
      const view = button("View routes");
      view.addEventListener("click", () => renderCustomerProfile(customer));
      const card = recordCard(customer.name, `${active.length} active`, [view]);
      card.insertBefore(element("p", { text: `${money(total)} monthly contract value` }), card.lastChild);
      rows.append(card);
    });
    section.append(rows);
    content.replaceChildren(section);
  }

  async function renderSubcontractors() {
    const records = await readJson("/api/subcontractors");
    const section = formSection("Subcontractors", "Maintain each company, its drivers and its vehicles. Archive preserves history.");
    const form = element("form", { className: "manager-form" }, [field("Company name", "company_name", { required: true, maxlength: "160" })]);
    const create = button("Review new subcontractor", "primary-button");
    form.append(element("div", { className: "manager-form-actions" }, [create]));
    form.addEventListener("submit", (event) => event.preventDefault());
    create.addEventListener("click", () => {
      if (!form.reportValidity()) return;
      const payload = toPayload(form);
      perform({ message: "Create this subcontractor?", summary: [["Company", payload.company_name]], url: "/api/subcontractors", payload, success: "Subcontractor created." });
    });
    section.append(form);
    const list = element("div", { className: "manager-record-list" });
    records.forEach((record) => {
      const addDriver = button("Add driver");
      const addVehicle = button("Add vehicle");
      const archive = button("Archive", "warning-button");
      addDriver.addEventListener("click", () => renderSubcontractorMemberForm(record, "driver"));
      addVehicle.addEventListener("click", () => renderSubcontractorMemberForm(record, "vehicle"));
      archive.addEventListener("click", () => perform({ message: "Archive this subcontractor?", summary: [["Company", record.company_name]], url: `/api/subcontractors/${record.id}/archive`, payload: {}, success: "Subcontractor archived." }));
      const actions = record.status === "active" ? [addDriver, addVehicle, archive] : [];
      const card = recordCard(record.company_name, record.status, actions);
      card.insertBefore(element("p", { text: `Drivers: ${record.drivers.map((item) => `${item.name}${item.contact_number ? ` (${item.contact_number})` : ""}`).join(", ") || "None recorded"}` }), card.lastChild);
      card.insertBefore(element("p", { text: `Vehicles: ${record.vehicles.map((item) => `${item.vehicle_number}${item.capacity ? ` · ${item.capacity} seats` : ""}`).join(", ") || "None recorded"}` }), card.lastChild);
      list.append(card);
    });
    section.append(records.length ? list : empty("No subcontractors recorded."));
    content.replaceChildren(section);
  }

  function renderSubcontractorMemberForm(contractor, kind) {
    const driver = kind === "driver";
    const section = formSection(`Add ${kind} · ${contractor.company_name}`);
    const form = element("form", { className: "manager-form" }, driver ? [
      field("Driver name", "name", { required: true, maxlength: "120" }),
      field("Contact number (optional)", "contact_number", { maxlength: "40" }),
    ] : [
      field("Vehicle number", "vehicle_number", { required: true, maxlength: "32" }),
      field("Capacity / seaters (optional)", "capacity", { type: "number", min: "1" }),
    ]);
    const back = button("Cancel");
    const save = button(`Review ${kind}`, "primary-button");
    back.addEventListener("click", renderSubcontractors);
    save.addEventListener("click", () => {
      if (!form.reportValidity()) return;
      const payload = toPayload(form, driver ? [] : ["capacity"]);
      perform({ message: `Add this ${kind} to ${contractor.company_name}?`, summary: driver ? [["Driver", payload.name], ["Contact", payload.contact_number]] : [["Vehicle", payload.vehicle_number], ["Capacity", payload.capacity]], url: `/api/subcontractors/${contractor.id}/${driver ? "drivers" : "vehicles"}`, payload, success: `Subcontractor ${kind} added.` });
    });
    form.addEventListener("submit", (event) => event.preventDefault());
    form.append(element("div", { className: "manager-form-actions" }, [back, save]));
    section.append(form); content.replaceChildren(section);
  }

  async function renderMaintenance() {
    const [entries, fleet] = await Promise.all([readJson("/api/maintenance-entries"), readJson("/api/fleet")]);
    const section = formSection("Maintenance", "Every cost is linked to a vehicle for monthly profitability.");
    const form = element("form", { className: "manager-form" }, [
      field("Date", "service_date", { required: true, type: "date", value: todayValue() }),
      field("Vehicle", "vehicle_id", { required: true, options: [["", "Choose vehicle…"], ...fleet.map((item) => [String(item.id), item.registration_number])] }),
      field("Vendor", "vendor", { required: true, maxlength: "160" }),
      field("Type of service", "service_type", { required: true, maxlength: "120" }),
      field("Amount (SGD)", "amount", { required: true, type: "number", min: "0.01", step: "0.01" }),
      field("Remarks (optional)", "remarks", { maxlength: "300", wide: true }),
    ]);
    const create = button("Review maintenance expense", "primary-button");
    form.append(element("div", { className: "manager-form-actions" }, [create]));
    form.addEventListener("submit", (event) => event.preventDefault());
    create.addEventListener("click", () => {
      if (!form.reportValidity()) return;
      const payload = toPayload(form, ["vehicle_id"]);
      const vehicle = fleet.find((item) => item.id === payload.vehicle_id);
      perform({ message: "Record this vehicle maintenance expense?", summary: [["Date", payload.service_date], ["Vehicle", vehicle?.registration_number], ["Vendor", payload.vendor], ["Service", payload.service_type], ["Amount", money(payload.amount)]], url: "/api/maintenance-entries", payload, success: "Maintenance expense recorded." });
    });
    section.append(form);
    const list = element("div", { className: "manager-record-list" });
    entries.forEach((record) => {
      const card = recordCard(`${record.vehicle_number} · ${record.service_type}`, record.service_date);
      card.insertBefore(element("p", { text: `${record.vendor} · ${money(record.amount)}${record.remarks ? ` · ${record.remarks}` : ""}` }), card.lastChild);
      list.append(card);
    });
    section.append(entries.length ? list : empty("No maintenance expenses recorded."));
    content.replaceChildren(section);
  }

  async function renderProjects() {
    const records = await readJson("/api/projects");
    const section = formSection("Projects", "Create, edit or archive through ProjectService.");
    const createForm = element("form", { className: "manager-form" }, [
      field("Project name", "name", { required: true, maxlength: "200" }),
      field("Description (optional)", "description", { type: "textarea", wide: true }),
    ]);
    const createButton = button("Review new project", "primary-button");
    createForm.append(element("div", { className: "manager-form-actions" }, [createButton]));
    createForm.addEventListener("submit", (event) => event.preventDefault());
    createButton.addEventListener("click", () => {
      if (!createForm.reportValidity()) return;
      const payload = toPayload(createForm);
      perform({
        message: "Create this project?",
        summary: [["Name", payload.name], ["Description", payload.description]],
        url: "/api/projects", payload, success: "Project created.",
      });
    });
    section.append(createForm);

    const list = element("div", { className: "manager-record-list" });
    records.forEach((record) => {
      const edit = button("Edit");
      const archive = button("Archive", "warning-button");
      const actions = record.status === "active" ? [edit, archive] : [];
      const card = recordCard(record.name, record.status, actions);
      if (record.description) card.insertBefore(element("p", { text: record.description }), card.lastChild);
      edit.addEventListener("click", () => renderProjectEditor(record));
      archive.addEventListener("click", () => perform({
        message: "Archive this project?",
        summary: [["Project", record.name], ["Current status", record.status]],
        url: `/api/projects/${record.id}/archive`, payload: {}, success: "Project archived.",
      }));
      list.append(card);
    });
    section.append(records.length ? list : empty("No projects have been recorded."));
    content.replaceChildren(section);
  }

  function renderProjectEditor(record) {
    const section = formSection(`Edit ${record.name}`, "Only the existing name and description fields are available.");
    const form = element("form", { className: "manager-form" }, [
      field("Project name", "name", { required: true, maxlength: "200", value: record.name }),
      field("Description (optional)", "description", { type: "textarea", wide: true, value: record.description }),
    ]);
    const cancel = button("Cancel");
    const save = button("Review project edit", "primary-button");
    form.append(element("div", { className: "manager-form-actions" }, [cancel, save]));
    form.addEventListener("submit", (event) => event.preventDefault());
    cancel.addEventListener("click", renderProjects);
    save.addEventListener("click", () => {
      if (!form.reportValidity()) return;
      const payload = toPayload(form);
      perform({
        message: "Save these project changes?",
        summary: [["Name", payload.name], ["Description", payload.description]],
        url: `/api/projects/${record.id}/edit`, payload, success: "Project updated.",
      });
    });
    section.append(form);
    content.replaceChildren(section);
  }

  async function renderKnowledge() {
    const records = await readJson("/api/knowledge");
    const section = formSection("Knowledge", "Drafts can be edited or approved. Approved items are replaced forward, never edited in place.");
    const form = element("form", { className: "manager-form" }, [
      field("Title", "title", { required: true, maxlength: "300" }),
      field("Content", "content", { required: true, type: "textarea", wide: true, maxlength: "100000", rows: "6" }),
    ]);
    const create = button("Review new draft", "primary-button");
    form.append(element("div", { className: "manager-form-actions" }, [create]));
    form.addEventListener("submit", (event) => event.preventDefault());
    create.addEventListener("click", () => {
      if (!form.reportValidity()) return;
      const payload = toPayload(form);
      perform({ message: "Create this knowledge draft?", summary: [["Title", payload.title], ["Content", payload.content]], url: "/api/knowledge", payload, success: "Knowledge draft created." });
    });
    section.append(form);

    const list = element("div", { className: "manager-record-list" });
    records.forEach((record) => {
      const actions = [];
      if (record.status === "draft") {
        const edit = button("Edit draft");
        edit.addEventListener("click", () => renderKnowledgeEditor(record));
        const approve = button("Approve", "primary-button");
        approve.addEventListener("click", async () => perform({
          message: "Approve this exact saved knowledge draft?",
          summary: [["Title", record.title], ["Complete content", record.content], ["Saved version", record.updated_at]],
          url: `/api/knowledge/${record.id}/approve`,
          payload: {
            expected_updated_at: record.updated_at,
            expected_content_sha256: await sha256Hex(record.content),
          },
          success: "Knowledge item approved.",
        }));
        actions.push(edit, approve);
      }
      if (["draft", "approved"].includes(record.status)) {
        if (record.status === "approved") {
          const replace = button("Create replacement");
          replace.addEventListener("click", () => perform({ message: "Create a forward-only draft replacement?", summary: [["Approved item", record.title]], url: `/api/knowledge/${record.id}/replacement`, payload: {}, success: "Replacement draft created." }));
          actions.push(replace);
        }
        const archive = button("Archive", "warning-button");
        archive.addEventListener("click", () => perform({ message: "Archive this knowledge item?", summary: [["Title", record.title], ["Status", record.status]], url: `/api/knowledge/${record.id}/archive`, payload: {}, success: "Knowledge item archived." }));
        actions.push(archive);
      }
      const card = recordCard(record.title, record.status, actions);
      card.insertBefore(element("p", { className: "manager-record-preview", text: record.content }), card.lastChild);
      list.append(card);
    });
    section.append(records.length ? list : empty("No knowledge items have been recorded."));
    content.replaceChildren(section);
  }

  function renderKnowledgeEditor(record) {
    const section = formSection(`Edit draft: ${record.title}`, "Approved, archived and superseded records cannot be edited in place.");
    const form = element("form", { className: "manager-form" }, [
      field("Title", "title", { required: true, maxlength: "300", value: record.title }),
      field("Content", "content", { required: true, type: "textarea", wide: true, maxlength: "100000", rows: "8", value: record.content }),
    ]);
    const cancel = button("Cancel");
    const save = button("Review draft edit", "primary-button");
    form.append(element("div", { className: "manager-form-actions" }, [cancel, save]));
    form.addEventListener("submit", (event) => event.preventDefault());
    cancel.addEventListener("click", renderKnowledge);
    save.addEventListener("click", () => {
      if (!form.reportValidity()) return;
      const payload = toPayload(form);
      perform({ message: "Save these draft changes?", summary: [["Title", payload.title], ["Content", payload.content]], url: `/api/knowledge/${record.id}/edit`, payload, success: "Knowledge draft updated." });
    });
    section.append(form);
    content.replaceChildren(section);
  }

  const vehicleDetailDefinitions = [
    ["Registered owner", "registered_owner_id", "company"],
    ["Manufacture year", "manufacture_year", "number"],
    ["Passenger capacity", "passenger_capacity", "number"],
    ["Vehicle type", "vehicle_type", "vehicle_type"],
    ["Propellant", "propellant"], ["Scheme", "scheme"],
    ["Chassis number", "chassis_number"], ["Engine number", "engine_number"],
    ["Original registration date", "original_registration_date", "date"],
    ["Lifespan expiry", "lifespan_expiry", "date"], ["COE expiry", "coe_expiry", "date"],
    ["Primary colour", "primary_colour"], ["Unladen weight (kg)", "unladen_weight_kg", "decimal"],
    ["Maximum laden weight (kg)", "maximum_laden_weight_kg", "decimal"],
    ["Parking provider", "parking_provider"], ["Parking location", "parking_location"],
    ["Parking monthly cost (GST inclusive)", "parking_monthly_cost", "decimal"],
    ["Insurance provider", "insurance_provider"], ["Insurance annual amount (GST inclusive)", "insurance_annual_amount", "decimal"],
    ["Road tax amount", "road_tax_amount", "decimal"], ["Road tax period", "road_tax_period_months", "road_tax"],
    ["Finance company", "finance_company"], ["Original loan amount", "original_loan_amount", "decimal"],
    ["Monthly instalment", "monthly_instalment", "decimal"], ["Loan start date", "loan_start_date", "date"],
    ["Loan term (months)", "loan_term_months", "number"],
  ];

  async function renderFleet() {
    const fleet = await readJson("/api/fleet");
    const section = formSection("Fleet", "Create a company or vehicle, then maintain only the approved Fleet fields.");
    const forms = element("div", { className: "manager-split" });
    const companyForm = element("form", { className: "manager-form manager-subform" }, [field("Registered company name", "name", { required: true, maxlength: "160" })]);
    const addCompany = button("Review new company", "primary-button");
    companyForm.append(element("div", { className: "manager-form-actions" }, [addCompany]));
    companyForm.addEventListener("submit", (event) => event.preventDefault());
    addCompany.addEventListener("click", () => {
      if (!companyForm.reportValidity()) return;
      const payload = toPayload(companyForm);
      perform({ message: "Create this registered company?", summary: [["Company", payload.name]], url: "/api/legal-entities", payload, success: "Registered company created." });
    });
    const vehicleForm = element("form", { className: "manager-form manager-subform" }, [
      field("Registration number", "registration_number", { required: true, maxlength: "32" }),
      field("Make/model (optional)", "make_model", { maxlength: "120" }),
    ]);
    const addVehicle = button("Review new vehicle", "primary-button");
    vehicleForm.append(element("div", { className: "manager-form-actions" }, [addVehicle]));
    vehicleForm.addEventListener("submit", (event) => event.preventDefault());
    addVehicle.addEventListener("click", () => {
      if (!vehicleForm.reportValidity()) return;
      const payload = toPayload(vehicleForm);
      perform({ message: "Create this vehicle?", summary: [["Registration", payload.registration_number], ["Make/model", payload.make_model]], url: "/api/vehicles", payload, success: "Vehicle created." });
    });
    forms.append(companyForm, vehicleForm);
    section.append(forms);

    const list = element("div", { className: "manager-record-list" });
    fleet.vehicles.forEach((vehicle) => {
      const details = button("Edit details");
      details.addEventListener("click", () => renderVehicleEditor(vehicle, fleet.companies));
      const statusSelect = element("select", { "aria-label": `Status for ${vehicle.registration_number}` });
      [["active", "Active"], ["out_of_service", "Out of service"], ["retired", "Retired"]].forEach(([value, text]) => statusSelect.append(element("option", { value, text })));
      statusSelect.value = vehicle.status;
      const reviewStatus = button("Review status");
      reviewStatus.addEventListener("click", () => perform({ message: "Change this vehicle status?", summary: [["Vehicle", vehicle.registration_number], ["New status", statusSelect.value]], url: `/api/vehicles/${vehicle.id}/status`, payload: { status: statusSelect.value }, success: "Vehicle status updated." }));
      const card = recordCard(vehicle.registration_number, vehicle.status, [details, statusSelect, reviewStatus]);
      card.insertBefore(element("p", { text: `${displayValue(vehicle.make_model)} · ${displayValue(vehicle.vehicle_type)} · ${displayValue(vehicle.passenger_capacity)} seats` }), card.lastChild);
      list.append(card);
    });
    section.append(fleet.vehicles.length ? list : empty("No vehicles have been recorded."));
    content.replaceChildren(section);
  }

  function renderVehicleEditor(vehicle, companies) {
    const section = formSection(`Fleet details: ${vehicle.registration_number}`, "Blank optional values are stored as not recorded. Calculated balances remain service-owned.");
    const form = element("form", { className: "manager-form manager-details-form" });
    vehicleDetailDefinitions.forEach(([label, name, kind]) => {
      let options = { value: vehicle[name] };
      if (kind === "company") options.options = [["", "Not recorded"], ...companies.map((company) => [String(company.id), company.name])];
      else if (kind === "vehicle_type") options.options = [["", "Not recorded"], ["Bus", "Bus"], ["lorry", "Lorry"], ["car", "Car"]];
      else if (kind === "road_tax") options.options = [["", "Not recorded"], ["6", "6 months"], ["12", "12 months"]];
      else if (kind === "date") options.type = "date";
      else if (kind === "number") Object.assign(options, { type: "number", min: "0", step: "1" });
      else if (kind === "decimal") Object.assign(options, { type: "number", min: "0", step: "0.01" });
      form.append(field(label, name, options));
    });
    const cancel = button("Cancel");
    const save = button("Review Fleet details", "primary-button");
    form.append(element("div", { className: "manager-form-actions manager-field-wide" }, [cancel, save]));
    form.addEventListener("submit", (event) => event.preventDefault());
    cancel.addEventListener("click", renderFleet);
    save.addEventListener("click", () => {
      if (!form.reportValidity()) return;
      const numeric = ["registered_owner_id", "manufacture_year", "passenger_capacity", "unladen_weight_kg", "maximum_laden_weight_kg", "parking_monthly_cost", "insurance_annual_amount", "road_tax_amount", "road_tax_period_months", "original_loan_amount", "monthly_instalment", "loan_term_months"];
      const payload = toPayload(form, numeric);
      perform({ message: "Save these Fleet details?", summary: vehicleDetailDefinitions.map(([label, name]) => [label, payload[name]]), url: `/api/vehicles/${vehicle.id}/details`, payload, success: "Fleet details updated." });
    });
    section.append(form);
    content.replaceChildren(section);
  }

  const registerConfig = {
    drivers: { title: "Drivers", endpoint: "/api/drivers", nameLabel: "Driver name", reference: "employee_reference", referenceLabel: "Employee reference (optional)", statuses: [["active", "Active"], ["unavailable", "Unavailable"], ["retired", "Retired"]] },
    customers: { title: "Customers", endpoint: "/api/customers", nameLabel: "Customer name", reference: "customer_reference", referenceLabel: "Customer reference (optional)", statuses: [["active", "Active"], ["inactive", "Inactive"]] },
  };

  const weekdayOptions = [
    [0, "Mon"], [1, "Tue"], [2, "Wed"], [3, "Thu"],
    [4, "Fri"], [5, "Sat"], [6, "Sun"],
  ];

  const schedulePresets = [
    { value: "mon-fri", label: "Monday to Friday", weekdays: [0, 1, 2, 3, 4], remarks: "Excludes public holidays" },
    { value: "mon-sat", label: "Monday to Saturday", weekdays: [0, 1, 2, 3, 4, 5], remarks: "Monday to Saturday" },
    { value: "mon-sun", label: "Monday to Sunday", weekdays: [0, 1, 2, 3, 4, 5, 6], remarks: "Includes public holidays" },
    { value: "weekend-ph", label: "Saturday, Sunday & public holidays", weekdays: [5, 6], remarks: "Weekend / public holiday service" },
  ];
  const matchingSchedulePreset = (selected = []) => schedulePresets.find((preset) => preset.weekdays.length === selected.length && preset.weekdays.every((day) => selected.includes(day)));

  const weekdayFields = (selected = []) => {
    const wrapper = element("fieldset", { className: "manager-field manager-field-wide" });
    wrapper.append(element("legend", { text: "Operating schedule" }));
    const choices = element("div", { className: "manager-inline-options" });
    const selectedPreset = matchingSchedulePreset(selected);
    schedulePresets.forEach((preset) => {
      const input = element("input", { type: "radio", name: "schedule_preset", value: preset.value, required: true });
      input.checked = selectedPreset?.value === preset.value;
      choices.append(element("label", {}, [input, document.createTextNode(preset.label)]));
    });
    wrapper.append(choices);
    return wrapper;
  };

  const parseTimedStops = (value) => {
    const lines = value.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
    if (!lines.length) throw new Error("Enter at least one timed stop.");
    return lines.map((line, index) => {
      const match = line.match(/^([01]\d|2[0-3]):([0-5]\d)\s*\|\s*(.{1,160})$/);
      if (!match) throw new Error(`Stop ${index + 1} must use HH:MM | Location.`);
      return {
        stop_order: index,
        scheduled_time: `${match[1]}:${match[2]}:00`,
        location_name: match[3].trim(),
      };
    });
  };

  const recurringServiceForm = (customer, routes, existing = null) => {
    const section = formSection(
      existing ? `Replace ${existing.service_reference}` : `New recurring service for ${customer.name}`,
      "This is a fixed monthly tender service. It is never converted into a daily rate. Use one timed stop per line as HH:MM | Location."
    );
    const days = existing ? existing.days.map((item) => item.weekday) : [];
    const stops = existing
      ? existing.stops.map((stop) => `${String(stop.scheduled_time).slice(0, 5)} | ${stop.location_name}`).join("\n")
      : "";
    const form = element("form", { className: "manager-form" }, [
      field("Service reference", "service_reference", { required: true, maxlength: "40", value: existing?.service_reference }),
      field("Route", "route_id", { required: true, options: [["", "Select route"], ...routes.map((route) => [String(route.id), `${route.route_code}: ${route.origin} → ${route.destination}`])], value: existing?.route_id }),
      field("Vehicle requirement (as stated)", "vehicle_requirement", { maxlength: "200", value: existing?.vehicle_requirement }),
      field("Fixed monthly amount", "monthly_amount", { required: true, type: "number", min: "0", step: "0.01", value: existing?.monthly_amount }),
      field("Currency", "currency_code", { required: true, maxlength: "3", value: existing?.currency_code || "SGD" }),
      field("Effective start", "effective_start_date", { required: true, type: "date", value: existing ? "" : todayValue() }),
      field("Effective end (optional)", "effective_end_date", { type: "date", value: existing?.effective_end_date }),
      weekdayFields(days),
      field("Timed stops", "stops_text", { required: true, type: "textarea", wide: true, rows: "6", maxlength: "4000", value: stops }),
    ]);
    const cancel = button("Back to customer");
    const submit = button(existing ? "Review replacement" : "Review recurring service", "primary-button");
    form.append(element("div", { className: "manager-form-actions" }, [cancel, submit]));
    form.addEventListener("submit", (event) => event.preventDefault());
    cancel.addEventListener("click", () => renderCustomerProfile(customer));
    submit.addEventListener("click", () => {
      if (!form.reportValidity()) return;
      try {
        const payload = toPayload(form, ["route_id"]);
        delete payload.stops_text;
        const preset = schedulePresets.find((item) => item.value === form.elements.schedule_preset.value);
        if (!preset) throw new Error("Select one operating schedule.");
        payload.weekdays = [...preset.weekdays];
        payload.stops = parseTimedStops(form.elements.stops_text.value);
        if (!existing) payload.customer_id = customer.id;
        perform({
          message: existing ? "Create this forward replacement and archive the current service?" : "Create this recurring customer service?",
          summary: [
            ["Customer", customer.name], ["Reference", payload.service_reference],
            ["Operating schedule", preset.label], ["Trip remarks", preset.remarks],
            ["Fixed monthly amount", `${payload.currency_code} ${payload.monthly_amount}`],
            ["Effective start", payload.effective_start_date],
          ],
          url: existing ? `/api/recurring-services/${existing.id}/replacement` : "/api/recurring-services",
          payload,
          success: existing ? "Recurring service replaced." : "Recurring service created.",
        });
      } catch (error) {
        setStatus(error.message, "error");
      }
    });
    section.append(form);
    content.replaceChildren(section);
  };

  const fuelRuleForm = (customer, service, currentRule = null) => {
    const section = formSection(
      `Fuel terms · ${service.service_reference}`,
      "Enter only the terms written in this customer's contract. No default is assumed. The result is a draft indication and never creates an invoice."
    );
    const form = element("form", { className: "manager-form" }, [
      field("Effective from", "effective_from", { required: true, type: "date", value: todayValue() }),
      field("Contract baseline diesel price (SGD/L)", "baseline_price_per_litre", { required: true, type: "number", min: "0.0001", step: "0.0001", value: currentRule?.baseline_price_per_litre }),
      field("Fuel share of monthly contract (%)", "fuel_cost_share_percent", { required: true, type: "number", min: "0", max: "100", step: "0.0001", value: currentRule?.fuel_cost_share_percent }),
      field("Contract tolerance (%)", "tolerance_percent", { required: true, type: "number", min: "0", max: "100", step: "0.0001", value: currentRule?.tolerance_percent }),
    ]);
    const back = button("Back to customer");
    const save = button("Review contract fuel terms", "primary-button");
    form.append(element("div", { className: "manager-form-actions" }, [back, save]));
    form.addEventListener("submit", (event) => event.preventDefault());
    back.addEventListener("click", () => renderCustomerProfile(customer));
    save.addEventListener("click", () => {
      if (!form.reportValidity()) return;
      const payload = toPayload(form);
      perform({
        message: "Save these contract-specific fuel terms as a new effective record?",
        summary: [
          ["Service", service.service_reference],
          ["Effective from", payload.effective_from],
          ["Baseline", `${payload.baseline_price_per_litre} SGD/L`],
          ["Fuel share", `${payload.fuel_cost_share_percent}%`],
          ["Tolerance", `${payload.tolerance_percent}%`],
        ],
        url: `/api/recurring-services/${service.id}/fuel-rules`,
        payload,
        success: "Contract fuel terms saved.",
      });
    });
    section.append(form);
    content.replaceChildren(section);
  };

  async function renderCustomerProfile(customer) {
    const [services, routes, assignments, fleet, drivers, subcontractors] = await Promise.all([
      readJson(`/api/customers/${customer.id}/recurring-services`),
      readJson("/api/routes"),
      readJson("/api/recurring-route-assignments"),
      readJson("/api/fleet"),
      readJson("/api/drivers"),
      readJson("/api/subcontractors"),
    ]);
    const routeById = indexedById(routes);
    const assignmentByService = new Map(assignments.filter((item) => item.status === "active").map((item) => [item.recurring_service_id, item]));
    const draftResults = await Promise.allSettled(
      services.map((record) => readJson(`/api/recurring-services/${record.id}/fuel-adjustment`))
    );
    const fuelDraftByService = new Map(
      draftResults.flatMap((result, index) => result.status === "fulfilled"
        ? [[services[index].id, result.value]]
        : [])
    );
    const section = formSection(
      customer.name,
      "Recurring Services stay inside this customer profile. Ad-hoc work remains in dated Trips."
    );
    const back = button("Back to customers");
    const create = button("Add recurring service", "primary-button");
    back.addEventListener("click", () => renderRegister("customers"));
    create.addEventListener("click", () => recurringServiceForm(customer, routes));
    section.append(element("div", { className: "manager-form-actions" }, [back, create]));

    const list = element("div", { className: "manager-record-list" });
    services.forEach((record) => {
      const actions = [];
      if (record.status === "active") {
        const pause = button("Pause");
        pause.addEventListener("click", () => perform({ message: "Pause this recurring service?", summary: [["Service", record.service_reference]], url: `/api/recurring-services/${record.id}/status`, payload: { status: "paused" }, success: "Recurring service paused." }));
        const replace = button("Replace");
        replace.addEventListener("click", () => recurringServiceForm(customer, routes, record));
        actions.push(pause, replace);
      } else if (record.status === "paused") {
        const resume = button("Resume");
        resume.addEventListener("click", () => perform({ message: "Resume this recurring service?", summary: [["Service", record.service_reference]], url: `/api/recurring-services/${record.id}/status`, payload: { status: "active" }, success: "Recurring service resumed." }));
        actions.push(resume);
      }
      if (record.status !== "archived") {
        const archive = button("Archive", "warning-button");
        archive.addEventListener("click", () => perform({ message: "Archive this recurring service?", summary: [["Service", record.service_reference], ["Fixed monthly amount", `${record.currency_code} ${record.monthly_amount}`]], url: `/api/recurring-services/${record.id}/status`, payload: { status: "archived" }, success: "Recurring service archived." }));
        actions.push(archive);
        const fuelDraft = fuelDraftByService.get(record.id);
        const fuelTerms = button(fuelDraft?.current_rule ? "New fuel terms" : "Add fuel terms");
        fuelTerms.addEventListener("click", () => fuelRuleForm(customer, record, fuelDraft?.current_rule));
        actions.push(fuelTerms);
        const assign = button(assignmentByService.has(record.id) ? "Change assignment" : "Assign");
        assign.addEventListener("click", () => renderRecurringAssignmentForm(customer, record, fleet, drivers, subcontractors));
        actions.push(assign);
      }
      const route = routeById.get(record.route_id);
      const selectedDays = record.days.map((item) => item.weekday);
      const preset = matchingSchedulePreset(selectedDays);
      const dayNames = preset?.label || selectedDays.map((day) => weekdayOptions[day][1]).join(", ");
      const tripTime = record.stops.length ? String(record.stops[0].scheduled_time).slice(0, 5) : "Not recorded";
      const card = recordCard(record.service_reference, record.status, actions);
      card.insertBefore(element("p", { text: `${route?.route_code || `Route #${record.route_id}`} · Trip time ${tripTime} · ${dayNames} · ${record.currency_code} ${record.monthly_amount} monthly` }), card.lastChild);
      card.insertBefore(element("p", { text: record.stops.map((stop) => `${String(stop.scheduled_time).slice(0, 5)} ${stop.location_name}`).join(" → ") }), card.lastChild);
      if (preset) card.insertBefore(element("p", { className: "micro-copy left-copy", text: `Trip remarks: ${preset.remarks}` }), card.lastChild);
      const assignment = assignmentByService.get(record.id);
      if (assignment) {
        const provider = assignment.assignment_type === "own_fleet" ? "Own fleet" : assignment.subcontractor_name;
        card.insertBefore(element("p", { className: "assignment-summary", text: `Assigned: ${provider} · ${assignment.vehicle_number || "Vehicle not recorded"} · ${assignment.driver_name || "Driver not recorded"}${assignment.contact_number ? ` · ${assignment.contact_number}` : ""}${assignment.monthly_subcontractor_cost !== null ? ` · Cost ${money(assignment.monthly_subcontractor_cost)} monthly` : ""}` }), card.lastChild);
      } else {
        card.insertBefore(element("p", { className: "assignment-warning", text: "Unassigned route — needs attention" }), card.lastChild);
      }
      card.insertBefore(element("p", { className: "micro-copy left-copy", text: `${displayValue(record.vehicle_requirement)} · Effective ${record.effective_start_date}${record.effective_end_date ? ` to ${record.effective_end_date}` : " onward"}` }), card.lastChild);
      const fuelDraft = fuelDraftByService.get(record.id);
      if (fuelDraft?.calculation_status === "draft_ready") {
        card.insertBefore(element("p", {
          className: "fuel-draft-copy",
          text: `Draft fuel adjustment: ${fuelDraft.currency_code} ${fuelDraft.draft_adjustment_amount} · indicated monthly total ${fuelDraft.currency_code} ${fuelDraft.adjusted_monthly_amount} · benchmark ${fuelDraft.benchmark_price_per_litre}/L`,
        }), card.lastChild);
      } else if (fuelDraft) {
        const messages = {
          contract_terms_not_configured: "Fuel adjustment: contract terms not configured.",
          benchmark_stale: "Fuel adjustment paused: the last benchmark is stale.",
          benchmark_unavailable: "Fuel adjustment paused: no verified benchmark is available.",
        };
        card.insertBefore(element("p", {
          className: "micro-copy left-copy",
          text: messages[fuelDraft.calculation_status] || "Fuel adjustment is unavailable.",
        }), card.lastChild);
      }
      list.append(card);
    });
    section.append(services.length ? list : empty("No recurring services have been recorded for this customer."));
    content.replaceChildren(section);
  }

  function renderRecurringAssignmentForm(customer, service, fleet, drivers, subcontractors) {
    const activeContractors = subcontractors.filter((contractor) => contractor.status === "active");
    const subVehicles = activeContractors.flatMap((contractor) => contractor.vehicles.map((vehicle) => ({ ...vehicle, contractor })));
    const subDrivers = activeContractors.flatMap((contractor) => contractor.drivers.map((driver) => ({ ...driver, contractor })));
    const section = formSection(`Assign · ${service.service_reference}`, "Choose either an Advan vehicle or a subcontractor. A new assignment ends the prior active assignment but preserves its history.");
    const form = element("form", { className: "manager-form" }, [
      field("Assignment type", "assignment_type", { required: true, options: [["own_fleet", "Own driver and vehicle"], ["subcontractor", "Subcontractor"]] }),
      field("Effective start", "effective_start_date", { required: true, type: "date", value: todayValue() }),
      field("Own vehicle", "vehicle_id", { options: [["", "Choose vehicle…"], ...fleet.map((item) => [String(item.id), item.registration_number])] }),
      field("Own driver (optional)", "driver_id", { options: [["", "No driver recorded"], ...drivers.map((item) => [String(item.id), item.name])] }),
      field("Subcontractor vehicle", "subcontractor_vehicle_id", { options: [["", "Choose vehicle…"], ...subVehicles.map((item) => [String(item.id), `${item.contractor.company_name} · ${item.vehicle_number}`])] }),
      field("Subcontractor driver (optional)", "subcontractor_driver_id", { options: [["", "No driver recorded"], ...subDrivers.map((item) => [String(item.id), `${item.contractor.company_name} · ${item.name}`])] }),
      field("Fixed monthly subcontractor cost (SGD)", "monthly_subcontractor_cost", { type: "number", min: "0", step: "0.01" }),
      field("Remarks (optional)", "remarks", { maxlength: "300", wide: true }),
    ]);
    const type = form.elements.assignment_type;
    const sync = () => {
      const own = type.value === "own_fleet";
      [form.elements.vehicle_id, form.elements.driver_id].forEach((node) => { node.disabled = !own; });
      [form.elements.subcontractor_vehicle_id, form.elements.subcontractor_driver_id, form.elements.monthly_subcontractor_cost].forEach((node) => { node.disabled = own; });
      form.elements.vehicle_id.required = own;
      form.elements.subcontractor_vehicle_id.required = !own;
      form.elements.monthly_subcontractor_cost.required = !own;
    };
    type.addEventListener("change", sync); sync();
    const back = button("Cancel");
    const save = button("Review assignment", "primary-button");
    back.addEventListener("click", () => renderCustomerProfile(customer));
    form.addEventListener("submit", (event) => event.preventDefault());
    save.addEventListener("click", () => {
      if (!form.reportValidity()) return;
      const payload = toPayload(form, ["vehicle_id", "driver_id", "subcontractor_vehicle_id", "subcontractor_driver_id"]);
      payload.recurring_service_id = service.id;
      perform({ message: "Activate this route assignment?", summary: [["Route", service.service_reference], ["Type", payload.assignment_type], ["Effective start", payload.effective_start_date], ["Monthly subcontractor cost", payload.monthly_subcontractor_cost]], url: "/api/recurring-route-assignments", payload, success: "Route assignment activated." });
    });
    form.append(element("div", { className: "manager-form-actions" }, [back, save]));
    section.append(form); content.replaceChildren(section);
  }

  async function renderDriverProfile(driver) {
    const records = await readJson(`/api/drivers/${driver.id}/employment-records`);
    const section = formSection(
      driver.name,
      "Private Employment/Payroll history. These monthly SGD facts do not change operational driver availability."
    );
    const back = button("Back to drivers");
    back.addEventListener("click", () => renderRegister("drivers"));
    section.append(element("div", { className: "manager-form-actions" }, [back]));

    const form = element("form", { className: "manager-form" }, [
      field("Effective month", "effective_month", { required: true, type: "month", value: todayValue().slice(0, 7) }),
      field("Worker category", "worker_category", { required: true, options: [["local_pr", "Local / PR — CPF"], ["foreign_levy", "Foreign worker — levy"]] }),
      field("Monthly basic salary (SGD)", "basic_salary", { required: true, type: "number", min: "0", step: "0.01" }),
      field("Employer CPF amount (SGD)", "employer_cpf_amount", { type: "number", min: "0", step: "0.01" }),
      field("Monthly levy amount (SGD)", "monthly_levy_amount", { type: "number", min: "0", step: "0.01" }),
      field("Monthly incentive allowance (SGD)", "monthly_allowance", { type: "number", min: "0", step: "0.01" }),
      field("Employment status", "employment_status", { required: true, options: [["active", "Active"], ["inactive", "Inactive"]] }),
    ]);
    const category = form.elements.worker_category;
    const cpf = form.elements.employer_cpf_amount;
    const levy = form.elements.monthly_levy_amount;
    const syncCategory = () => {
      const local = category.value === "local_pr";
      cpf.disabled = !local;
      levy.disabled = local;
      if (local) levy.value = "";
      else cpf.value = "";
    };
    category.addEventListener("change", syncCategory);
    syncCategory();
    const submit = button("Review employment record", "primary-button");
    form.append(element("div", { className: "manager-form-actions" }, [submit]));
    form.addEventListener("submit", (event) => event.preventDefault());
    submit.addEventListener("click", () => {
      if (!form.reportValidity()) return;
      const payload = toPayload(form);
      payload.driver_id = driver.id;
      payload.effective_month = `${payload.effective_month}-01`;
      perform({
        message: "Create this effective-month employment record? Existing history will not be overwritten.",
        summary: [
          ["Driver", driver.name], ["Effective month", payload.effective_month.slice(0, 7)],
          ["Worker category", payload.worker_category], ["Basic salary", `SGD ${payload.basic_salary}`],
          ["Employer CPF", payload.employer_cpf_amount], ["Monthly levy", payload.monthly_levy_amount],
          ["Incentive allowance", payload.monthly_allowance], ["Employment status", payload.employment_status],
        ],
        url: "/api/driver-employment-records",
        payload,
        success: "Employment record created.",
      });
    });
    section.append(form);

    const list = element("div", { className: "manager-record-list" });
    records.forEach((record) => {
      const categoryLabel = record.worker_category === "local_pr" ? "Local / PR" : "Foreign worker with levy";
      const statutoryCost = record.worker_category === "local_pr"
        ? `Employer CPF SGD ${displayValue(record.employer_cpf_amount)}`
        : `Levy SGD ${displayValue(record.monthly_levy_amount)}`;
      const card = recordCard(record.effective_month.slice(0, 7), record.employment_status);
      card.insertBefore(element("p", { text: `${categoryLabel} · Basic salary SGD ${record.basic_salary}` }), card.lastChild);
      card.insertBefore(element("p", { text: `${statutoryCost} · Incentive allowance SGD ${displayValue(record.monthly_allowance)}` }), card.lastChild);
      list.append(card);
    });
    section.append(records.length ? list : empty("No employment/payroll history has been recorded for this driver."));
    content.replaceChildren(section);
  }

  async function renderRegister(kind) {
    const config = registerConfig[kind];
    const records = await readJson(config.endpoint);
    const detailResults = kind === "drivers"
      ? await Promise.allSettled(records.map((record) => readJson(`/api/drivers/${record.id}/employment-records`)))
      : kind === "customers"
        ? await Promise.allSettled(records.map((record) => readJson(`/api/customers/${record.id}/recurring-services`)))
        : [];
    const detailsById = new Map(records.map((record, index) => [record.id, detailResults[index]?.status === "fulfilled" ? detailResults[index].value : []]));
    const section = formSection(config.title, `Only the existing ${config.title.toLowerCase()} register fields are exposed.`);
    const search = field(`Search ${config.title.toLowerCase()}`, "search", { maxlength: "120" });
    section.append(search);
    const form = element("form", { className: "manager-form" }, [
      field(config.nameLabel, "name", { required: true, maxlength: kind === "drivers" ? "120" : "160" }),
      field(config.referenceLabel, config.reference, { maxlength: "40" }),
    ]);
    const create = button(`Review new ${kind === "drivers" ? "driver" : "customer"}`, "primary-button");
    form.append(element("div", { className: "manager-form-actions" }, [create]));
    form.addEventListener("submit", (event) => event.preventDefault());
    create.addEventListener("click", () => {
      if (!form.reportValidity()) return;
      const payload = toPayload(form);
      perform({ message: `Create this ${kind === "drivers" ? "driver" : "customer"}?`, summary: [["Name", payload.name], [config.referenceLabel, payload[config.reference]]], url: config.endpoint, payload, success: `${kind === "drivers" ? "Driver" : "Customer"} created.` });
    });
    section.append(form);
    const list = element("div", { className: "manager-record-list" });
    records.forEach((record) => {
      const select = element("select", { "aria-label": `Status for ${record.name}` });
      config.statuses.forEach(([value, text]) => select.append(element("option", { value, text })));
      select.value = record.status;
      const update = button("Review status");
      update.addEventListener("click", () => perform({ message: `Change ${record.name}'s status?`, summary: [["Name", record.name], ["New status", select.value]], url: `${config.endpoint}/${record.id}/status`, payload: { status: select.value }, success: "Status updated." }));
      const actions = [select, update];
      if (kind === "customers") {
        const profile = button("Open profile", "primary-button");
        profile.addEventListener("click", () => renderCustomerProfile(record));
        actions.unshift(profile);
      } else if (kind === "drivers") {
        const profile = button("Open private profile", "primary-button");
        profile.addEventListener("click", () => renderDriverProfile(record));
        actions.unshift(profile);
      }
      const card = recordCard(record.name, record.status, actions);
      if (kind === "drivers") {
        const latest = [...detailsById.get(record.id)].sort((a, b) => b.effective_month.localeCompare(a.effective_month))[0];
        const category = latest?.worker_category === "local_pr" ? "Local / PR" : latest?.worker_category === "foreign_levy" ? "Foreigner" : "Category not recorded";
        const cost = (value) => value === null || value === undefined ? "Not recorded" : money(value);
        card.insertBefore(element("p", { text: latest ? `${category} · Basic ${cost(latest.basic_salary)} · CPF ${cost(latest.employer_cpf_amount)} · Levy ${cost(latest.monthly_levy_amount)} · Allowance ${cost(latest.monthly_allowance)}` : "Employment costs not recorded" }), card.lastChild);
      } else if (kind === "customers") {
        const active = detailsById.get(record.id).filter((item) => item.status === "active");
        const total = active.reduce((sum, item) => sum + Number(item.monthly_amount || 0), 0);
        card.insertBefore(element("p", { text: `${money(total)} monthly contract value · ${active.length} active routes` }), card.lastChild);
      } else card.insertBefore(element("p", { text: displayValue(record[config.reference]) }), card.lastChild);
      card.dataset.searchText = card.textContent.toLowerCase();
      list.append(card);
    });
    search.querySelector("input").addEventListener("input", (event) => {
      const query = event.target.value.trim().toLowerCase();
      list.querySelectorAll(".manager-record").forEach((card) => { card.hidden = query && !card.dataset.searchText.includes(query); });
    });
    section.append(records.length ? list : empty(`No ${kind} have been recorded.`));
    content.replaceChildren(section);
  }

  async function renderRoutes() {
    const records = await readJson("/api/routes");
    const section = formSection("Routes", "Routes currently use only route code, origin, destination and status.");
    const form = element("form", { className: "manager-form" }, [
      field("Route code", "route_code", { required: true, maxlength: "40" }),
      field("Origin", "origin", { required: true, maxlength: "160" }),
      field("Destination", "destination", { required: true, maxlength: "160" }),
    ]);
    const create = button("Review new route", "primary-button");
    form.append(element("div", { className: "manager-form-actions" }, [create]));
    form.addEventListener("submit", (event) => event.preventDefault());
    create.addEventListener("click", () => {
      if (!form.reportValidity()) return;
      const payload = toPayload(form);
      perform({ message: "Create this route?", summary: [["Route code", payload.route_code], ["Origin", payload.origin], ["Destination", payload.destination]], url: "/api/routes", payload, success: "Route created." });
    });
    section.append(form);
    const list = element("div", { className: "manager-record-list" });
    records.forEach((record) => {
      const select = element("select", { "aria-label": `Status for ${record.route_code}` });
      [["active", "Active"], ["inactive", "Inactive"]].forEach(([value, text]) => select.append(element("option", { value, text })));
      select.value = record.status;
      const update = button("Review status");
      update.addEventListener("click", () => perform({ message: "Change this route status?", summary: [["Route", record.route_code], ["New status", select.value]], url: `/api/routes/${record.id}/status`, payload: { status: select.value }, success: "Route status updated." }));
      const card = recordCard(record.route_code, record.status, [select, update]);
      card.insertBefore(element("p", { text: `${record.origin} → ${record.destination}` }), card.lastChild);
      list.append(card);
    });
    section.append(records.length ? list : empty("No routes have been recorded."));
    content.replaceChildren(section);
  }

  async function renderTrips() {
    const [trips, routes] = await Promise.all([readJson("/api/trips"), readJson("/api/routes")]);
    const routeById = indexedById(routes);
    const section = formSection("Trips", "Trips are dated service records. Recurring customer schedules are not inferred here.");
    const form = element("form", { className: "manager-form" }, [
      field("Trip reference", "trip_reference", { required: true, maxlength: "40" }),
      field("Route", "route_id", { required: true, options: [["", "Select route"], ...routes.map((route) => [String(route.id), `${route.route_code}: ${route.origin} → ${route.destination}`])] }),
      field("Service date", "service_date", { required: true, type: "date", value: todayValue() }),
    ]);
    const create = button("Review new trip", "primary-button");
    form.append(element("div", { className: "manager-form-actions" }, [create]));
    form.addEventListener("submit", (event) => event.preventDefault());
    create.addEventListener("click", () => {
      if (!form.reportValidity()) return;
      const payload = toPayload(form, ["route_id"]);
      const route = routeById.get(payload.route_id);
      perform({
        message: "Create this dated trip?",
        summary: [["Trip reference", payload.trip_reference], ["Route", route ? route.route_code : payload.route_id], ["Service date", payload.service_date]],
        url: "/api/trips", payload, success: "Trip created.",
      });
    });
    section.append(form);
    const list = element("div", { className: "manager-record-list" });
    trips.forEach((record) => {
      const route = routeById.get(record.route_id);
      const select = element("select", { "aria-label": `Status for ${record.trip_reference}` });
      [["planned", "Planned"], ["completed", "Completed"], ["cancelled", "Cancelled"]].forEach(([value, text]) => select.append(element("option", { value, text })));
      select.value = record.status;
      const update = button("Review status");
      update.addEventListener("click", () => perform({
        message: "Change this trip status?",
        summary: [["Trip", record.trip_reference], ["Service date", record.service_date], ["New status", select.value]],
        url: `/api/trips/${record.id}/status`, payload: { status: select.value }, success: "Trip status updated.",
      }));
      const card = recordCard(record.trip_reference, record.status, [select, update]);
      card.insertBefore(element("p", { text: `${record.service_date} · ${route ? `${route.route_code}: ${route.origin} → ${route.destination}` : `Route #${record.route_id}`}` }), card.lastChild);
      list.append(card);
    });
    section.append(trips.length ? list : empty("No trips have been recorded."));
    content.replaceChildren(section);
  }

  async function renderAssignments() {
    const [assignments, trips, fleet, drivers] = await Promise.all([
      readJson("/api/trip-assignments"), readJson("/api/trips"), readJson("/api/fleet"), readJson("/api/drivers"),
    ]);
    const tripById = indexedById(trips);
    const vehicleById = indexedById(fleet.vehicles);
    const driverById = indexedById(drivers);
    const assignedTripIds = new Set(assignments.map((item) => item.trip_id));
    const assignableTrips = trips.filter((item) => item.status === "planned" && !assignedTripIds.has(item.id));
    const activeVehicles = fleet.vehicles.filter((item) => item.status === "active");
    const activeDrivers = drivers.filter((item) => item.status === "active");
    const section = formSection("Assignments", "One existing planned trip can be assigned once. Released records remain part of history.");
    const form = element("form", { className: "manager-form" }, [
      field("Planned trip", "trip_id", { required: true, options: [["", "Select trip"], ...assignableTrips.map((item) => [String(item.id), `${item.trip_reference} · ${item.service_date}`])] }),
      field("Active vehicle", "vehicle_id", { required: true, options: [["", "Select vehicle"], ...activeVehicles.map((item) => [String(item.id), item.registration_number])] }),
      field("Active driver", "driver_id", { required: true, options: [["", "Select driver"], ...activeDrivers.map((item) => [String(item.id), item.name])] }),
    ]);
    const create = button("Review assignment", "primary-button");
    form.append(element("div", { className: "manager-form-actions" }, [create]));
    form.addEventListener("submit", (event) => event.preventDefault());
    create.addEventListener("click", () => {
      if (!form.reportValidity()) return;
      const payload = toPayload(form, ["trip_id", "vehicle_id", "driver_id"]);
      perform({
        message: "Create this trip assignment?",
        summary: [["Trip", tripById.get(payload.trip_id)?.trip_reference], ["Vehicle", vehicleById.get(payload.vehicle_id)?.registration_number], ["Driver", driverById.get(payload.driver_id)?.name]],
        url: "/api/trip-assignments", payload, success: "Trip assignment created.",
      });
    });
    section.append(form);
    const list = element("div", { className: "manager-record-list" });
    assignments.forEach((record) => {
      const trip = tripById.get(record.trip_id);
      const vehicle = vehicleById.get(record.vehicle_id);
      const driver = driverById.get(record.driver_id);
      const actions = [];
      if (record.status === "assigned") {
        const release = button("Review release", "warning-button");
        release.addEventListener("click", () => perform({
          message: "Release this assignment?",
          summary: [["Trip", trip?.trip_reference], ["Vehicle", vehicle?.registration_number], ["Driver", driver?.name]],
          url: `/api/trip-assignments/${record.id}/release`, payload: {}, success: "Trip assignment released.",
        }));
        actions.push(release);
      }
      const card = recordCard(trip?.trip_reference || `Trip #${record.trip_id}`, record.status, actions);
      card.insertBefore(element("p", { text: `${vehicle?.registration_number || `Vehicle #${record.vehicle_id}`} · ${driver?.name || `Driver #${record.driver_id}`}` }), card.lastChild);
      list.append(card);
    });
    section.append(assignments.length ? list : empty("No trip assignments have been recorded."));
    content.replaceChildren(section);
  }

  async function renderFuelEntries() {
    const [entries, fleet] = await Promise.all([readJson("/api/fuel-entries"), readJson("/api/fleet")]);
    const vehicleById = indexedById(fleet.vehicles);
    const section = formSection("Fuel entries", "Fuel facts are append-only. Saved entries cannot be edited or deleted here.");
    const form = element("form", { className: "manager-form" }, [
      field("Vehicle", "vehicle_id", { required: true, options: [["", "Select vehicle"], ...fleet.vehicles.map((item) => [String(item.id), item.registration_number])] }),
      field("Recorded date", "recorded_on", { required: true, type: "date", value: todayValue() }),
      field("Litres", "litres", { required: true, type: "number", min: "0.01", step: "0.01" }),
      field("Total cost (optional)", "total_cost", { type: "number", min: "0", step: "0.01" }),
      field("Odometer km (optional)", "odometer_km", { type: "number", min: "0", step: "0.1" }),
    ]);
    const create = button("Review fuel entry", "primary-button");
    form.append(element("div", { className: "manager-form-actions" }, [create]));
    form.addEventListener("submit", (event) => event.preventDefault());
    create.addEventListener("click", () => {
      if (!form.reportValidity()) return;
      const payload = toPayload(form, ["vehicle_id"]);
      perform({
        message: "Record this immutable fuel entry?",
        summary: [["Vehicle", vehicleById.get(payload.vehicle_id)?.registration_number], ["Date", payload.recorded_on], ["Litres", payload.litres], ["Total cost", payload.total_cost], ["Odometer km", payload.odometer_km]],
        url: "/api/fuel-entries", payload, success: "Fuel entry recorded.",
      });
    });
    section.append(form);
    const list = element("div", { className: "manager-record-list" });
    entries.forEach((record) => {
      const vehicle = vehicleById.get(record.vehicle_id);
      const card = recordCard(vehicle?.registration_number || `Vehicle #${record.vehicle_id}`, record.recorded_on);
      card.insertBefore(element("p", { text: `${record.litres} L · Cost ${displayValue(record.total_cost)} · Odometer ${displayValue(record.odometer_km)}` }), card.lastChild);
      list.append(card);
    });
    section.append(entries.length ? list : empty("No fuel entries have been recorded."));
    content.replaceChildren(section);
  }

  async function renderFinance() {
    const [entries, trips, customers, fleet, assignments] = await Promise.all([readJson("/api/financial-entries"), readJson("/api/trips"), readJson("/api/customers"), readJson("/api/fleet"), readJson("/api/recurring-route-assignments")]);
    const tripById = indexedById(trips);
    const customerById = indexedById(customers);
    const vehicleById = indexedById(fleet);
    const serviceResults = await Promise.all(customers.map((customer) => readJson(`/api/customers/${customer.id}/recurring-services`)));
    const activeServices = serviceResults.flat().filter((item) => item.status === "active");
    const monthlyIncome = activeServices.reduce((sum, item) => sum + Number(item.monthly_amount || 0), 0);
    const monthlyLoans = fleet.reduce((sum, item) => sum + Number(item.monthly_instalment || 0), 0);
    const monthlySubcontractors = assignments.filter((item) => item.status === "active").reduce((sum, item) => sum + Number(item.monthly_subcontractor_cost || 0), 0);
    const knownMonthlyNet = monthlyIncome - monthlyLoans - monthlySubcontractors;
    const floating = entries.filter((item) => item.payment_status !== "paid" && !item.expected_payment_date);
    const section = formSection("Finance", "Management P&L uses the accounting month. Optional payment timing controls cash forecasts; missing timing stays floating and needs attention.");
    section.append(element("div", { className: "operations-metrics" }, [
      summaryMetric("Predictable monthly income", money(monthlyIncome), "Active customer routes"),
      summaryMetric("Monthly vehicle instalments", money(monthlyLoans), "Known fleet commitments"),
      summaryMetric("Monthly subcontractors", money(monthlySubcontractors), "Fixed recurring assignments"),
      summaryMetric("Known monthly balance", money(knownMonthlyNet), "Before fuel, payroll and other costs"),
      summaryMetric("Floating timing", String(floating.length), "Needs user attention"),
    ]));
    const form = element("form", { className: "manager-form" }, [
      field("Entry date", "entry_date", { required: true, type: "date", value: todayValue() }),
      field("Accounting / service month", "accounting_month", { required: true, type: "month", value: todayValue().slice(0, 7) }),
      field("Expected payment date (optional)", "expected_payment_date", { type: "date" }),
      field("Payment status", "payment_status", { required: true, options: [["unpaid", "Unpaid"], ["paid", "Paid"]] }),
      field("Actual payment date (optional)", "payment_date", { type: "date" }),
      field("Entry type", "entry_type", { required: true, options: [["income", "Income"], ["expense", "Expense"]] }),
      field("Category (optional)", "category", { maxlength: "40" }),
      field("Amount", "amount", { required: true, type: "number", min: "0.01", step: "0.01" }),
      field("Currency", "currency_code", { required: true, maxlength: "3", value: "SGD" }),
      field("Description (optional)", "description", { maxlength: "200", wide: true }),
      field("Trip (optional)", "trip_id", { options: [["", "Not linked"], ...trips.map((item) => [String(item.id), `${item.trip_reference} · ${item.service_date}`])] }),
      field("Customer (optional)", "customer_id", { options: [["", "Not linked"], ...customers.map((item) => [String(item.id), item.name])] }),
      field("Vehicle (optional)", "vehicle_id", { options: [["", "Not linked"], ...fleet.map((item) => [String(item.id), item.registration_number])] }),
    ]);
    const create = button("Review financial entry", "primary-button");
    form.append(element("div", { className: "manager-form-actions" }, [create]));
    form.addEventListener("submit", (event) => event.preventDefault());
    create.addEventListener("click", () => {
      if (!form.reportValidity()) return;
      const payload = toPayload(form, ["trip_id", "customer_id", "vehicle_id"]);
      payload.accounting_month = `${payload.accounting_month}-01`;
      perform({
        message: "Record this immutable financial entry?",
        summary: [["Accounting month", payload.accounting_month.slice(0, 7)], ["Expected payment", payload.expected_payment_date || "Floating — needs attention"], ["Type", payload.entry_type], ["Amount", `${payload.currency_code} ${payload.amount}`], ["Description", payload.description], ["Customer", customerById.get(payload.customer_id)?.name], ["Vehicle", vehicleById.get(payload.vehicle_id)?.registration_number]],
        url: "/api/financial-entries", payload, success: "Financial entry recorded.",
      });
    });
    section.append(form);
    const list = element("div", { className: "manager-record-list" });
    entries.forEach((record) => {
      const links = [tripById.get(record.trip_id)?.trip_reference, customerById.get(record.customer_id)?.name, vehicleById.get(record.vehicle_id)?.registration_number].filter(Boolean).join(" · ");
      const timing = record.payment_status === "paid" ? `Paid ${record.payment_date}` : (record.expected_payment_date || "Floating — needs attention");
      const card = recordCard(`${record.currency_code} ${record.amount}`, `${record.entry_type} · ${record.accounting_month.slice(0, 7)}`);
      card.insertBefore(element("p", { text: `${timing} · ${displayValue(record.category)} · ${displayValue(record.description)}${links ? ` · ${links}` : ""}` }), card.lastChild);
      list.append(card);
    });
    section.append(entries.length ? list : empty("No financial entries have been recorded."));
    content.replaceChildren(section);
  }

  async function renderActivity() {
    const records = await readJson("/api/activity-log");
    const section = formSection("Activity Log", "Read-only history produced by approved application services.");
    const list = element("div", { className: "manager-record-list" });
    records.forEach((record) => {
      const entity = [displayValue(record.entity_type), displayValue(record.entity_id)].join(" #");
      const card = recordCard(displayValue(record.action), record.created_at);
      card.insertBefore(element("p", { text: `${entity}${record.details ? ` · ${record.details}` : ""}` }), card.lastChild);
      list.append(card);
    });
    section.append(records.length ? list : empty("No activity has been recorded."));
    content.replaceChildren(section);
  }

  async function renderActiveTab() {
    content.replaceChildren(element("p", { className: "manager-loading", text: "Loading local records…" }));
    setStatus("");
    try {
      if (activeTab === "dashboard") await renderDashboard();
      else if (activeTab === "projects") await renderProjects();
      else if (activeTab === "knowledge") await renderKnowledge();
      else if (activeTab === "fleet") await renderFleet();
      else if (activeTab === "routes") await renderRouteWorkspace();
      else if (activeTab === "trips") await renderTrips();
      else if (activeTab === "assignments") await renderAssignments();
      else if (activeTab === "fuel-entries") await renderFuelEntries();
      else if (activeTab === "finance") await renderFinance();
      else if (activeTab === "subcontractors") await renderSubcontractors();
      else if (activeTab === "maintenance") await renderMaintenance();
      else if (activeTab === "activity") await renderActivity();
      else await renderRegister(activeTab);
    } catch (error) {
      content.replaceChildren(empty("This section could not be loaded."));
      setStatus(error.message, "error");
    }
  }

  const setActiveTab = (tab) => {
    activeTab = tab;
    document.querySelectorAll("[data-manager-tab]").forEach((node) => {
      const active = node.dataset.managerTab === tab;
      node.classList.toggle("active", active);
      node.setAttribute("aria-selected", String(active));
    });
    renderActiveTab();
  };

  const openManager = (tab = "dashboard") => {
    manager.hidden = false;
    backdrop.hidden = true;
    document.body.classList.add("record-manager-open");
    byId("manage-records").setAttribute("aria-expanded", "true");
    setActiveTab(tab);
  };

  const closeManager = () => {
    manager.hidden = false;
    backdrop.hidden = true;
    setActiveTab("dashboard");
  };

  byId("manage-records").setAttribute("aria-expanded", "false");
  byId("manage-records").addEventListener("click", () => openManager());
  document.querySelectorAll("[data-open-manager]").forEach((node) => node.addEventListener("click", () => openManager(node.dataset.openManager)));
  document.querySelectorAll("[data-manager-tab]").forEach((node) => node.addEventListener("click", () => setActiveTab(node.dataset.managerTab)));
  byId("close-record-manager").addEventListener("click", closeManager);
  backdrop.addEventListener("click", closeManager);
  byId("cancel-edit-confirmation").addEventListener("click", () => resolveConfirmation(false));
  byId("confirm-edit-action").addEventListener("click", () => resolveConfirmation(true));
  confirmation.addEventListener("cancel", (event) => { event.preventDefault(); resolveConfirmation(false); });
  openManager("dashboard");
})();
