"use strict";

const $ = (id) => document.getElementById(id);

const els = {
  form: $("convert-form"),
  tabUrl: $("tab-url"),
  tabFile: $("tab-file"),
  panelUrl: $("panel-url"),
  panelFile: $("panel-file"),
  urlInput: $("url-input"),
  clearBtn: $("clear-btn"),
  previewBtn: $("preview-btn"),
  preview: $("preview"),
  previewThumb: $("preview-thumb"),
  previewTitle: $("preview-title"),
  previewMeta: $("preview-meta"),
  fileInput: $("file-input"),
  dropzone: $("dropzone"),
  dropzoneText: $("dropzone-text"),
  dropzoneHint: $("dropzone-hint"),
  kindInputs: document.querySelectorAll('input[name="kind"]'),
  chips: $("format-chips"),
  qualityField: $("quality-field"),
  qualityLabel: $("quality-label"),
  qualitySelect: $("quality-select"),
  specContainer: $("spec-container"),
  specCodec: $("spec-codec"),
  specQuality: $("spec-quality"),
  specSize: $("spec-size"),
  formatNote: $("format-note"),
  submitBtn: $("submit-btn"),
  progress: $("progress"),
  wave: $("wave"),
  elapsed: $("elapsed"),
  status: $("status"),
  banner: $("banner"),
};

const state = {
  mode: "url",
  kind: "audio",
  format: "mp3",
  catalogue: null,
  busy: false,
  timer: null,
};

/* What each output format is made of, for the details panel. */
const FORMAT_INFO = {
  mp3: { label: "MP3", container: "MP3", codec: "MP3 (LAME)" },
  m4a: { label: "M4A", container: "M4A", codec: "AAC" },
  aac: { label: "AAC", container: "AAC stream", codec: "AAC" },
  wav: { label: "WAV", container: "WAV", codec: "PCM, 16-bit" },
  flac: { label: "FLAC", container: "FLAC", codec: "FLAC, lossless" },
  ogg: { label: "OGG", container: "OGG", codec: "Vorbis" },
  opus: { label: "Opus", container: "Opus", codec: "Opus" },
  mp4: { label: "MP4", container: "MP4", codec: "Usually H.264 and AAC" },
  webm: { label: "WebM", container: "WebM", codec: "Usually VP9 and Opus" },
  mkv: { label: "MKV", container: "MKV", codec: "Usually H.264 and AAC" },
  sony_mp4: {
    label: "Sony car MP4",
    container: "MP4",
    codec: "MPEG-4 and AAC",
    quality: "Up to 720 x 576, 30 fps",
    size: "About 26 MB per minute",
    note: "Made for the Sony XAV-W650BT. Older car units cannot play H.264 video.",
  },
  sony_avi: {
    label: "Sony car AVI",
    container: "AVI",
    codec: "Xvid and MP3",
    quality: "Up to 720 x 576, 30 fps",
    size: "About 50 MB per minute",
    note: "Also for the Sony XAV-W650BT. Try this one if the Sony car MP4 will not play.",
  },
};

/* Rough video sizes per minute at each resolution. They vary a lot with the video. */
const VIDEO_SIZE_PER_MINUTE = {
  360: "3 to 6 MB",
  480: "6 to 9 MB",
  720: "15 to 25 MB",
  1080: "30 to 50 MB",
};

/* ---------- helpers ---------- */

function setStatus(message, kind = "") {
  els.status.textContent = message;
  els.status.className = "status" + (kind ? ` is-${kind}` : "");
}

function formatClock(seconds) {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

function formatDuration(seconds) {
  if (!seconds) return "Unknown length";
  const h = Math.floor(seconds / 3600);
  const rest = seconds % 3600;
  const m = Math.floor(rest / 60);
  const s = Math.floor(rest % 60);
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

/* ---------- busy state and waveform ---------- */

function buildWave() {
  const heights = [30, 55, 80, 45, 95, 60, 35, 75, 100, 50, 70, 40, 90, 65, 30, 85, 55, 100, 45, 75, 35, 60, 90, 50];
  heights.forEach((height, index) => {
    const bar = document.createElement("span");
    bar.style.setProperty("--h", height);
    bar.style.setProperty("--i", index);
    els.wave.appendChild(bar);
  });
}

function setBusy(busy, { showProgress = false } = {}) {
  state.busy = busy;
  els.submitBtn.disabled = busy;
  els.previewBtn.disabled = busy;
  els.submitBtn.textContent = busy && showProgress ? "Converting..." : "Convert and download";

  clearInterval(state.timer);
  els.progress.hidden = !(busy && showProgress);
  if (busy && showProgress) {
    const started = Date.now();
    const tick = () => {
      els.elapsed.textContent = `Working for ${formatClock((Date.now() - started) / 1000)}. Long videos can take a few minutes.`;
    };
    tick();
    state.timer = setInterval(tick, 1000);
  }
}

/* ---------- formats, quality and details panel ---------- */

function formatsForKind(kind) {
  return state.catalogue[kind].map((f) => f.id);
}

function renderChips() {
  els.chips.replaceChildren();
  for (const id of formatsForKind(state.kind)) {
    const label = document.createElement("label");
    label.className = "chip";

    const input = document.createElement("input");
    input.type = "radio";
    input.name = "format";
    input.value = id;
    input.checked = id === state.format;

    const text = document.createElement("span");
    text.textContent = FORMAT_INFO[id]?.label || id.toUpperCase();

    label.append(input, text);
    els.chips.appendChild(label);
  }
}

function isLossless() {
  return state.catalogue.lossless_audio.includes(state.format);
}

function isPreset() {
  return state.catalogue.video.some((f) => f.id === state.format && f.preset);
}

function renderQualityOptions() {
  const c = state.catalogue;
  const isAudio = state.kind === "audio";

  els.qualityField.hidden = isLossless() || isPreset();
  els.qualitySelect.replaceChildren();
  els.qualityLabel.textContent = isAudio ? "Bitrate" : "Maximum resolution";

  for (const value of isAudio ? c.audio_bitrates : c.video_heights) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = isAudio ? `${value} kbps` : value === "best" ? "Best available" : `${value}p`;
    els.qualitySelect.appendChild(option);
  }
  els.qualitySelect.value = isAudio ? c.defaults.audio_bitrate : c.defaults.video_height;
}

function renderSpec() {
  const info = FORMAT_INFO[state.format] || { container: state.format, codec: "" };
  const quality = els.qualitySelect.value;
  let qualityText;
  let sizeText;

  if (isPreset()) {
    qualityText = info.quality;
    sizeText = info.size;
  } else if (state.kind === "audio") {
    if (isLossless()) {
      qualityText = "Lossless";
      sizeText = state.format === "wav" ? "About 10 MB per minute" : "About 5 to 7 MB per minute";
    } else {
      qualityText = `${quality} kbps`;
      sizeText = `About ${((Number(quality) * 60) / 8 / 1000).toFixed(1)} MB per minute`;
    }
  } else if (quality === "best") {
    qualityText = "Best available";
    sizeText = "Depends on the video";
  } else {
    qualityText = `Up to ${quality}p`;
    sizeText = `About ${VIDEO_SIZE_PER_MINUTE[quality]} per minute`;
  }

  els.specContainer.textContent = info.container;
  els.specCodec.textContent = info.codec;
  els.specQuality.textContent = qualityText;
  els.specSize.textContent = sizeText;
  els.formatNote.textContent = info.note || "";
  els.formatNote.hidden = !info.note;
}

function selectKind(kind) {
  state.kind = kind;
  state.format = kind === "audio" ? "mp3" : "mp4";
  renderChips();
  renderQualityOptions();
  renderSpec();
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
  selectKind("audio");
}

/* ---------- source tabs ---------- */

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

function onTabKeys(event) {
  if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
  const next = state.mode === "url" ? "file" : "url";
  selectTab(next);
  (next === "url" ? els.tabUrl : els.tabFile).focus();
}

/* ---------- link preview ---------- */

function updateClearButton() {
  els.clearBtn.hidden = !els.urlInput.value;
}

function clearUrl() {
  els.urlInput.value = "";
  els.preview.hidden = true;
  updateClearButton();
  els.urlInput.focus();
}

async function previewUrl() {
  const url = els.urlInput.value.trim();
  if (!url) {
    setStatus("Paste a video link first.", "error");
    els.urlInput.focus();
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
      .join(", ");
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
    els.dropzoneText.textContent = "Choose an audio or video file, or drop it here";
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
  const format = state.format;
  const quality = els.qualityField.hidden ? "" : els.qualitySelect.value;

  if (state.mode === "url") {
    const url = els.urlInput.value.trim();
    if (!url) throw new Error("Paste a video link first.");
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

  setBusy(true, { showProgress: true });
  setStatus("");
  try {
    const response = await requestConversion();
    if (!response.ok) throw new Error(await errorMessage(response));

    const blob = await response.blob();
    const name = filenameFrom(response, `converted.${state.format}`);
    saveBlob(blob, name);
    setStatus(`Done: ${name} (${formatSize(blob.size)})`, "success");
  } catch (error) {
    setStatus(error.message || "Something went wrong.", "error");
  } finally {
    setBusy(false);
  }
}

/* ---------- setup check ---------- */

async function checkSetup() {
  try {
    const response = await fetch("/api/health");
    const health = await response.json();
    if (!health.ffmpeg) {
      els.banner.textContent =
        "FFmpeg was not found on this computer, so conversions will fail. " +
        "Install it (Windows: winget install Gyan.FFmpeg), open a new terminal, " +
        "and restart MediaForge. The README has more help.";
      els.banner.hidden = false;
    }
  } catch (_) { /* loadFormats reports an unreachable server */ }
}

/* ---------- init ---------- */

els.tabUrl.addEventListener("click", () => selectTab("url"));
els.tabFile.addEventListener("click", () => selectTab("file"));
els.tabUrl.addEventListener("keydown", onTabKeys);
els.tabFile.addEventListener("keydown", onTabKeys);

for (const input of els.kindInputs) {
  input.addEventListener("change", () => input.checked && state.catalogue && selectKind(input.value));
}
els.chips.addEventListener("change", (event) => {
  if (event.target.name !== "format") return;
  state.format = event.target.value;
  renderQualityOptions();
  renderSpec();
});
els.qualitySelect.addEventListener("change", renderSpec);

els.urlInput.addEventListener("input", updateClearButton);
els.clearBtn.addEventListener("click", clearUrl);
els.previewBtn.addEventListener("click", previewUrl);
els.form.addEventListener("submit", onSubmit);

buildWave();
setupDropzone();
loadFormats();
checkSetup();
