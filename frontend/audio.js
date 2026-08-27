"use strict";

/*
 * This is a transport hook, not an active transcription client. A future
 * provider adapter must advertise readiness before microphone permission is
 * requested. Captured audio must never auto-submit an Owner Goal.
 */

function voiceSocketUrl() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}/ws/transcription`;
}

async function createMemoryOnlyRecorder(stream) {
  const recorder = new MediaRecorder(stream);
  recorder.addEventListener("dataavailable", () => {
    // Intentionally discard chunks until a governed provider adapter exists.
  });
  recorder.addEventListener("stop", () => {
    stream.getTracks().forEach((track) => track.stop());
  });
  return recorder;
}

function configureVoiceHook() {
  const button = document.getElementById("voice-button");
  const status = document.getElementById("voice-status");
  if (!button || !status) return;

  button.addEventListener("click", () => {
    button.disabled = true;
    status.textContent = "Checking the local voice boundary…";
    const socket = new WebSocket(voiceSocketUrl());

    socket.addEventListener("message", (event) => {
      const message = JSON.parse(event.data);
      status.textContent = message.message || "Voice provider is unavailable.";
      if (message.state === "ready") {
        status.textContent = "Voice transport ready. Microphone confirmation is still required.";
      }
    });

    socket.addEventListener("close", () => {
      button.disabled = false;
    });

    socket.addEventListener("error", () => {
      status.textContent = "The local voice hook could not be reached.";
      button.disabled = false;
    });
  });
}

document.addEventListener("DOMContentLoaded", configureVoiceHook);

// Retained as an explicit future hook and deliberately not called in this task.
window.AdvanCoreVoice = { createMemoryOnlyRecorder };
