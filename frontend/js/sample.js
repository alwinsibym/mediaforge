/* "Try a 10-second sample": convert a short piece with the chosen settings and estimate the rest. */

import { $ } from "./dom.js";
import { formatSize } from "./format.js";
import { problemFrom, setProblem } from "./errors.js";
import { buildFileForm } from "./upload-form.js";

const box = {
  root: $("sample-box"),
  button: $("sample-btn"),
  result: $("sample-result"),
  estimate: $("sample-estimate"),
  player: $("sample-player"),
  note: $("sample-note"),
};

let busy = false;

function about(seconds) {
  if (seconds < 5) return "a few seconds";
  if (seconds < 90) return `about ${Math.round(seconds / 5) * 5} seconds`;
  const minutes = seconds / 60;
  if (minutes < 90) return `about ${Math.round(minutes)} minutes`;
  return `about ${(minutes / 60).toFixed(1)} hours`;
}

function playerFor(sample) {
  const kind = sample.kind;
  let element;
  if (["gif", "webp"].includes(kind)) {
    element = document.createElement("img");
    element.alt = "Sample of the result";
  } else if (["mp4", "webm", "mkv"].includes(kind)) {
    element = document.createElement("video");
    element.controls = true;
    element.muted = false;
    element.playsInline = true;
  } else {
    element = document.createElement("audio");
    element.controls = true;
  }
  element.src = sample.url;
  element.className = "sample-media";
  return element;
}

export function showSampleBox(visible, hasFile) {
  box.root.hidden = !visible;
  box.button.disabled = busy || !hasFile;
}

/* The choices changed after a sample was made, so what it shows is out of date. */
export function markSampleStale() {
  if (box.result.hidden) return;
  box.result.classList.add("is-stale");
  box.note.textContent = "You changed something. Try the sample again to see the new result.";
}

export function clearSample() {
  box.result.hidden = true;
  box.result.classList.remove("is-stale");
  box.player.replaceChildren();
  box.note.textContent = "";
}

export async function makeSample() {
  if (busy) return;
  let data;
  try {
    data = buildFileForm({ forSample: true });
  } catch (error) {
    setProblem(error, "Choose a file first.");
    return;
  }
  busy = true;
  box.button.disabled = true;
  box.button.textContent = "Making the sample...";
  box.root.classList.add("is-working");
  box.note.textContent = "Uploading and converting ten seconds. A long file may take a moment to upload.";
  try {
    const response = await fetch("/api/sample", { method: "POST", body: data });
    if (!response.ok) throw await problemFrom(response);
    const sample = await response.json();
    clearSample();
    box.estimate.textContent = `The whole file: ${formatSize(sample.estimated_bytes)}, converting takes ${about(sample.estimated_seconds)}.`;
    box.player.append(playerFor(sample));
    box.result.hidden = false;
    box.note.textContent = `This is ${Math.round(sample.sample_seconds)} seconds from the middle. The size is an estimate.`;
  } catch (error) {
    clearSample();
    box.note.textContent = error.message || "The sample could not be made.";
  } finally {
    busy = false;
    box.button.textContent = "Try a 10-second sample";
    box.button.disabled = false;
    box.root.classList.remove("is-working");
  }
}

export function wireSample() {
  box.button.addEventListener("click", makeSample);
}
