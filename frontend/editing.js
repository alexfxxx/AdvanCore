"use strict";

(() => {
  const byId = (id) => document.getElementById(id);
  const manager = byId("record-manager");
  const backdrop = byId("record-manager-backdrop");
  const content = byId("record-manager-content");
  const statusLine = byId("record-manager-status");
  const confirmation = byId("edit-confirmation");
  const summaryList = byId("edit-confirmation-summary");
  let activeTab = "projects";
  let previouslyFocused = null;
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

  async function renderRegister(kind) {
    const config = registerConfig[kind];
    const records = await readJson(config.endpoint);
    const section = formSection(config.title, `Only the existing ${config.title.toLowerCase()} register fields are exposed.`);
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
      const card = recordCard(record.name, record.status, [select, update]);
      card.insertBefore(element("p", { text: displayValue(record[config.reference]) }), card.lastChild);
      list.append(card);
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

  async function renderActiveTab() {
    content.replaceChildren(element("p", { className: "manager-loading", text: "Loading local records…" }));
    setStatus("");
    try {
      if (activeTab === "projects") await renderProjects();
      else if (activeTab === "knowledge") await renderKnowledge();
      else if (activeTab === "fleet") await renderFleet();
      else if (activeTab === "routes") await renderRoutes();
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

  const openManager = (tab = "projects") => {
    previouslyFocused = document.activeElement;
    manager.hidden = false;
    backdrop.hidden = false;
    document.body.classList.add("record-manager-open");
    byId("manage-records").setAttribute("aria-expanded", "true");
    setActiveTab(tab);
    byId("close-record-manager").focus();
  };

  const closeManager = () => {
    manager.hidden = true;
    backdrop.hidden = true;
    document.body.classList.remove("record-manager-open");
    byId("manage-records").setAttribute("aria-expanded", "false");
    if (previouslyFocused) previouslyFocused.focus();
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
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !manager.hidden && !confirmation.open) closeManager();
  });
})();
