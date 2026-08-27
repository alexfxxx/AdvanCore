"use strict";

const byId = (id) => document.getElementById(id);

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

function configureGoalForm() {
  const form = byId("owner-goal-form");
  const input = byId("owner-goal");
  const submit = form.querySelector("button[type='submit']");

  input.addEventListener("input", () => {
    setText("goal-count", `${input.value.length} / 2000`);
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    submit.disabled = true;
    showGoalResult("Validating through the governed dry-run controller…");
    try {
      const preview = await requestJson("/api/owner-goals/preview", {
        method: "POST",
        body: JSON.stringify({ goal: input.value }),
      });
      const lines = [
        `Status: ${preview.status}`,
        `Candidate task: ${preview.candidate_task_id || "not assigned"}`,
        `Task written: ${preview.task_written ? "yes" : "no"}`,
        `Worker launched: ${preview.planner_launched ? "yes" : "no"}`,
        `Next: ${preview.next_action}`,
      ];
      showGoalResult(lines.join("\n"), !preview.accepted);
    } catch (error) {
      showGoalResult(error.message, true);
    } finally {
      submit.disabled = false;
    }
  });
}

document.addEventListener("DOMContentLoaded", () => {
  configureGoalForm();
  Promise.allSettled([loadStatus(), loadProjects(), loadKnowledge()]);
});
