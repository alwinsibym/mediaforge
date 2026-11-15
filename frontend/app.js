"use strict";

const $ = (id) => document.getElementById(id);

const els = {
  form: $("convert-form"),
  tabUrl: $("tab-url"),
  tabFile: $("tab-file"),
  panelUrl: $("panel-url"),
  panelFile: $("panel-file"),
  urlInput: $("url-input"),
  previewBtn: $("preview-btn"),
  preview: $("preview"),
  previewThumb: $("preview-thumb"),
  previewTitle: $("preview-title"),
  previewMeta: $("preview-meta"),
  fileInput: $("file-input"),
  dropzone: $("dropzone"),
  dropzoneText: $("dropzone-text"),
  dropzoneHint: $("dropzone-hint"),
  formatSelect: $("format-select"),
  qualityField: $("quality-field"),
  qualityLabel: $("quality-label"),
  qualitySelect: $("quality-select"),
  submitBtn: $("submit-btn"),
  status: $("status"),
};

const state = { mode: "url", catalogue: null, busy: false };

/* ---------- helpers ---------- */

function setStatus(message, kind = "") {
  els.status.textContent = message;
  els.status.className = "status" + (kind ? ` is-${kind}` : "");
}

function formatDuration(seconds) {
  if (!seconds) return "Unknown length";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  const mmss = `${String(m).padStart(h ? 2 : 1, "0")}:${String(s).padStart(2, "0")}`;
  return h ? `${h}:${mmss}` : mmss;
}

function formatSize(bytes) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

async function errorMessage(response) {
  try {
    const body = await response.json();
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) return "Please check your input and try again.";
  } catch (_) { /* not JSON */ }
  return `The server returned an error (${response.status}).`;
}

function filenameFrom(response, fallback) {
  const header = response.headers.get("content-disposition") || "";
  const encoded = header.match(/filename\*=(?:UTF-8|utf-8)''([^;]+)/);
  if (encoded) {
    try { return decodeURIComponent(encoded[1]); } catch (_) { /* fall through */ }
  }
  const plain = header.match(/filename="?([^";]+)"?/);
  return plain ? plain[1] : fallback;
}

function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}

function setBusy(busy) {
  state.busy = busy;
  els.submitBtn.disabled = busy;
  els.previewBtn.disabled = busy;
  els.submitBtn.textContent = busy ? "Converting..." : "Convert and download";
}

/* ---------- formats and quality ---------- */

function optionGroup(label, items) {
  const group = document.createElement("optgroup");
  group.label = label;
  for (const item of items) {
    const option = document.createElement("option");
    option.value = item.id;
    option.textContent = item.label;
    group.appendChild(option);
  }
  return group;
}

function updateQualityOptions() {
  const c = state.catalogue;
  const format = els.formatSelect.value;
  const isAudio = c.audio.some((f) => f.id === format);
  const isLossless = c.lossless_audio.includes(format);

  els.qualityField.hidden = isLossless;
  els.qualitySelect.replaceChildren();

  const values = isAudio ? c.audio_bitrates : c.video_heights;
  els.qualityLabel.textContent = isAudio ? "Bitrate" : "Maximum resolution";
  for (const value of values) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = isAudio ? `${value} kbps` : value === "best" ? "Best available" : `${value}p`;
    els.qualitySelect.appendChild(option);
  }
  els.qualitySelect.value = isAudio ? c.defaults.audio_bitrate : c.defaults.video_height;
}

async function loadFormats() {
  try {
    const response = await fetch("/api/formats");
    if (!response.ok) throw new Error();
    state.catalogue = await response.json();
  } catch (_) {
    setStatus("Can't reach the MediaForge server. Is it running?", "error");
    els.submitBtn.disabled = true;
    return;
  }
  els.formatSelect.append(
    optionGroup("Audio", state.catalogue.audio),
    optionGroup("Video", state.catalogue.video),
  );
  els.formatSelect.value = "mp3";
  updateQualityOptions();
}

/* ---------- tabs ---------- */

function selectTab(mode) {
  state.mode = mode;
  const isUrl = mode === "url";
  els.tabUrl.setAttribute("aria-selected", String(isUrl));
  els.tabFile.setAttribute("aria-selected", String(!isUrl));
  els.tabUrl.tabIndex = isUrl ? 0 : -1;
  els.tabFile.tabIndex = isUrl ? -1 : 0;
  els.panelUrl.hidden = !isUrl;
  els.panelFile.hidden = isUrl;
  setStatus("");
}

/* ---------- URL preview ---------- */

async function previewUrl() {
  const url = els.urlInput.value.trim();
  if (!url) {
    setStatus("Enter a URL first.", "error");
    return;
  }
  setBusy(true);
  setStatus("Looking up the video...");
  try {
    const response = await fetch("/api/info", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    if (!response.ok) throw new Error(await errorMessage(response));
    const info = await response.json();

    els.previewTitle.textContent = info.title;
    els.previewMeta.textContent = [info.uploader, formatDuration(info.duration)]
      .filter(Boolean)
      .join(" - ");
    if (info.thumbnail) {
      els.previewThumb.src = info.thumbnail;
      els.previewThumb.hidden = false;
    } else {
      els.previewThumb.hidden = true;
    }
    els.preview.hidden = false;
    setStatus("");
  } catch (error) {
    els.preview.hidden = true;
    setStatus(error.message, "error");
  } finally {
    setBusy(false);
  }
}

/* ---------- file selection ---------- */

function showSelectedFile() {
  const file = els.fileInput.files[0];
  if (!file) {
    els.dropzoneText.textContent = "Choose a file or drag it here";
    els.dropzoneHint.textContent = "";
    return;
  }
  els.dropzoneText.textContent = file.name;
  els.dropzoneHint.textContent = formatSize(file.size);
}

function setupDropzone() {
  els.fileInput.addEventListener("change", showSelectedFile);

  for (const type of ["dragenter", "dragover"]) {
    els.dropzone.addEventListener(type, (event) => {
      event.preventDefault();
      els.dropzone.classList.add("is-over");
    });
  }
  for (const type of ["dragleave", "drop"]) {
    els.dropzone.addEventListener(type, (event) => {
      event.preventDefault();
      els.dropzone.classList.remove("is-over");
    });
  }
  els.dropzone.addEventListener("drop", (event) => {
    if (event.dataTransfer.files.length) {
      els.fileInput.files = event.dataTransfer.files;
      showSelectedFile();
    }
  });
}

/* ---------- convert ---------- */

async function requestConversion() {
  const format = els.formatSelect.value;
  const quality = els.qualityField.hidden ? "" : els.qualitySelect.value;

  if (state.mode === "url") {
    const url = els.urlInput.value.trim();
    if (!url) throw new Error("Enter a URL first.");
    return fetch("/api/convert", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, format, quality: quality || null }),
    });
  }

  const file = els.fileInput.files[0];
  if (!file) throw new Error("Choose a file first.");
  const limitMb = state.catalogue.limits.max_upload_mb;
  if (file.size > limitMb * 1024 * 1024) {
    throw new Error(`That file is larger than the ${limitMb} MB limit.`);
  }
  const data = new FormData();
  data.append("file", file);
  data.append("format", format);
  if (quality) data.append("quality", quality);
  return fetch("/api/convert-file", { method: "POST", body: data });
}

async function onSubmit(event) {
  event.preventDefault();
  if (state.busy || !state.catalogue) return;

  setBusy(true);
  setStatus("Converting. Long videos and large files can take a few minutes.");
  try {
    const response = await requestConversion();
    if (!response.ok) throw new Error(await errorMessage(response));

    const blob = await response.blob();
    const name = filenameFrom(response, `converted.${els.formatSelect.value}`);
    saveBlob(blob, name);
    setStatus(`Done: ${name} (${formatSize(blob.size)})`, "success");
  } catch (error) {
    setStatus(error.message || "Something went wrong.", "error");
  } finally {
    setBusy(false);
  }
}

/* ---------- init ---------- */

els.tabUrl.addEventListener("click", () => selectTab("url"));
els.tabFile.addEventListener("click", () => selectTab("file"));
els.formatSelect.addEventListener("change", () => state.catalogue && updateQualityOptions());
els.previewBtn.addEventListener("click", previewUrl);
els.form.addEventListener("submit", onSubmit);
setupDropzone();
loadFormats();
