"use strict";

const byId = (id) => document.getElementById(id);
let localActionToken = null;
let approvedPreviewGoal = null;
let activeRunId = null;
let progressStream = null;

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
  Promise.allSettled([
    loadLocalActionSession(),
    loadStatus(),
    loadProjects(),
    loadKnowledge(),
    recoverCurrentJob(),
  ]);
});
