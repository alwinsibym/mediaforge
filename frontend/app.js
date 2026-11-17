"use strict";

const $ = (id) => document.getElementById(id);

const els = {
  form: $("convert-form"),
  tabUrl: $("tab-url"),
  tabFile: $("tab-file"),
  tabPlaylist: $("tab-playlist"),
  panelUrl: $("panel-url"),
  panelFile: $("panel-file"),
  panelPlaylist: $("panel-playlist"),
  playlistInput: $("playlist-input"),
  playlistLoad: $("playlist-load"),
  playlistBox: $("playlist-box"),
  playlistTitle: $("playlist-title"),
  playlistCount: $("playlist-count"),
  playlistAll: $("playlist-all"),
  playlistList: $("playlist-list"),
  optFolder: $("opt-folder"),
  optZip: $("opt-zip"),
  folderHint: $("folder-hint"),
  job: $("job"),
  jobSummary: $("job-summary"),
  jobCancel: $("job-cancel"),
  jobBar: $("job-bar"),
  jobItems: $("job-items"),
  jobDetail: $("job-detail"),
  meter: $("meter"),
  meterFill: $("meter-fill"),
  meterPercent: $("meter-percent"),
  progressText: $("progress-text"),
  progressCancel: $("progress-cancel"),
  themeSwitch: $("theme-switch"),
  jobActions: $("job-actions"),
  jobOpen: $("job-open"),
  jobZip: $("job-zip"),
  urlInput: $("url-input"),
  clearBtn: $("clear-btn"),
  previewBtn: $("preview-btn"),
  preview: $("preview"),
  previewThumb: $("preview-thumb"),
  previewTitle: $("preview-title"),
  previewMeta: $("preview-meta"),
  previewQuality: $("preview-quality"),
  thumbTools: $("thumb-tools"),
  thumbSize: $("thumb-size"),
  thumbFormat: $("thumb-format"),
  thumbSquare: $("thumb-square"),
  thumbDownload: $("thumb-download"),
  muteField: $("mute-field"),
  optMute: $("opt-mute"),
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
  playlist: null,
  jobId: null,
  poller: null,
  info: null,
  previewedUrl: "",
  previewTimer: null,
  jobKind: "single",
  jobStarted: 0,
  upload: null,
};

const TABS = {
  url: { tab: "tab-url", panel: "panel-url" },
  file: { tab: "tab-file", panel: "panel-file" },
  playlist: { tab: "tab-playlist", panel: "panel-playlist" },
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
  mp4: { label: "MP4", container: "MP4", codec: "H.264 up to 1080p, VP9 above" },
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
  1440: "50 to 90 MB",
  2160: "100 to 200 MB",
  4320: "400 MB or more",
};

const RESOLUTION_NAMES = { 1440: "2K", 2160: "4K", 4320: "8K" };

function heightOf(quality) {
  return Number.parseInt(quality, 10) || 0;
}

function staticQualityLabel(value) {
  if (value === "best") return "Best available";
  const name = RESOLUTION_NAMES[value];
  return name ? `Up to ${value}p (${name})` : `Up to ${value}p`;
}

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

function formatSpeed(bytesPerSecond) {
  if (!bytesPerSecond) return "";
  if (bytesPerSecond < 1024 * 1024) return `${Math.max(1, Math.round(bytesPerSecond / 1024))} KB/s`;
  return `${(bytesPerSecond / (1024 * 1024)).toFixed(1)} MB/s`;
}

function formatTimeLeft(seconds) {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return "";
  const total = Math.max(1, Math.round(seconds));
  if (total < 60) return `about ${total} s left`;
  if (total < 3600) {
    const minutes = Math.floor(total / 60);
    const rest = total % 60;
    return `about ${minutes} min${rest ? ` ${rest} s` : ""} left`;
  }
  return `about ${Math.floor(total / 3600)} h ${Math.round((total % 3600) / 60)} min left`;
}

const PHASE_TEXT = {
  uploading: "Uploading",
  queued: "Starting",
  "looking up": "Looking up the video",
  downloading: "Downloading",
  processing: "Processing",
  converting: "Converting",
  retrying: "The site hiccupped, trying again",
};

/* One line such as "Downloading 42% - 3.2 MB/s - about 18 s left". */
function describeProgress(item) {
  const label = PHASE_TEXT[item.phase] || "Working";
  const percent = typeof item.percent === "number" ? ` ${Math.floor(item.percent)}%` : "";
  return [label + percent, formatSpeed(item.speed), formatTimeLeft(item.eta)]
    .filter(Boolean)
    .join(" \u00b7 ");
}

function setMeter(percent) {
  const known = typeof percent === "number";
  els.meter.classList.toggle("is-indeterminate", !known);
  els.meterFill.style.width = known ? `${percent}%` : "";
  els.meterPercent.textContent = known ? `${Math.floor(percent)}%` : "";
  if (known) els.meter.setAttribute("aria-valuenow", String(Math.floor(percent)));
  else els.meter.removeAttribute("aria-valuenow");
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

function submitLabel() {
  if (state.mode !== "playlist") return "Convert and download";
  const count = selectedEntries().length;
  if (!state.playlist) return "Load a playlist first";
  return count === 1 ? "Convert 1 video" : `Convert ${count} videos`;
}

function setBusy(busy, { showProgress = false } = {}) {
  state.busy = busy;
  els.submitBtn.disabled = busy;
  els.previewBtn.disabled = busy;
  els.playlistLoad.disabled = busy;
  els.submitBtn.textContent = busy && showProgress ? "Converting..." : submitLabel();

  clearInterval(state.timer);
  els.progress.hidden = !(busy && showProgress);
  if (busy && showProgress) {
    const started = Date.now();
    setMeter(null);
    els.progressText.textContent = "Starting...";
    const tick = () => {
      els.elapsed.textContent = `Elapsed ${formatClock((Date.now() - started) / 1000)}`;
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

  const previous = els.qualitySelect.value;
  const found = !isAudio && state.mode === "url" && state.info && state.info.qualities;
  els.qualityField.hidden = isLossless() || isPreset();
  els.qualitySelect.replaceChildren();
  els.qualityLabel.textContent = isAudio ? "Bitrate" : found?.length ? "Quality" : "Maximum resolution";

  const addOption = (value, text) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = text;
    els.qualitySelect.appendChild(option);
  };

  if (isAudio) {
    for (const value of c.audio_bitrates) addOption(value, `${value} kbps`);
    els.qualitySelect.value = c.defaults.audio_bitrate;
  } else if (found?.length) {
    // Only what this video really offers, so nothing is upscaled.
    for (const q of found) {
      addOption(q.id, q.size ? `${q.label} (about ${formatSize(q.size)})` : q.label);
    }
    els.qualitySelect.value = found.some((q) => q.id === previous) ? previous : found[0].id;
  } else {
    const heights = [...c.video_heights].sort((a, b) => heightOf(b) - heightOf(a));
    for (const value of heights) addOption(value, staticQualityLabel(value));
    const keep = heights.includes(previous) ? previous : c.defaults.video_height;
    els.qualitySelect.value = keep;
  }
  els.muteField.hidden = isAudio;
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
  } else if (state.mode === "url" && state.info?.qualities?.some((q) => q.id === quality)) {
    const chosen = state.info.qualities.find((q) => q.id === quality);
    qualityText = chosen.label;
    sizeText = chosen.size ? `About ${formatSize(chosen.size)} in total` : "Depends on the video";
  } else if (quality === "best") {
    qualityText = "Best available";
    sizeText = "Depends on the video";
  } else {
    const height = heightOf(quality);
    qualityText = `Up to ${height}p`;
    sizeText = VIDEO_SIZE_PER_MINUTE[height]
      ? `About ${VIDEO_SIZE_PER_MINUTE[height]} per minute`
      : "Depends on the video";
  }

  els.specContainer.textContent = info.container;
  const muted = isMuted() && !isPreset();
  els.specCodec.textContent = muted ? `${info.codec} (no sound)` : info.codec;
  els.specQuality.textContent = qualityText;
  els.specSize.textContent = sizeText;
  const note = info.note || highResolutionNote();
  els.formatNote.textContent = note;
  els.formatNote.hidden = !note;
}

function isMuted() {
  return state.kind === "video" && els.optMute.checked;
}

function highResolutionNote() {
  if (state.kind !== "video" || isPreset() || els.qualityField.hidden) return "";
  const quality = els.qualitySelect.value;
  const height = quality === "best" ? 9999 : heightOf(quality);
  if (height <= 1080 || state.format === "webm") return "";
  return "Above 1080p, YouTube offers VP9 and AV1 video instead of H.264. MKV or WebM plays these most reliably, and MP4 may not play on older devices.";
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
  for (const [name, ids] of Object.entries(TABS)) {
    const tab = $(ids.tab);
    const active = name === mode;
    tab.setAttribute("aria-selected", String(active));
    tab.tabIndex = active ? 0 : -1;
    $(ids.panel).hidden = !active;
  }
  els.submitBtn.textContent = submitLabel();
  els.submitBtn.disabled = mode === "playlist" && selectedEntries().length === 0;
  if (state.catalogue) {
    renderQualityOptions();
    renderSpec();
  }
  setStatus("");
}

function onTabKeys(event) {
  if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
  const names = Object.keys(TABS);
  const step = event.key === "ArrowRight" ? 1 : -1;
  const next = names[(names.indexOf(state.mode) + step + names.length) % names.length];
  selectTab(next);
  $(TABS[next].tab).focus();
}

/* ---------- link preview ---------- */

function updateClearButton() {
  els.clearBtn.hidden = !els.urlInput.value;
}

function resetPreview() {
  clearTimeout(state.previewTimer);
  state.info = null;
  state.previewedUrl = "";
  els.preview.hidden = true;
  els.thumbTools.hidden = true;
  if (state.catalogue) {
    renderQualityOptions();
    renderSpec();
  }
}

function clearUrl() {
  els.urlInput.value = "";
  resetPreview();
  updateClearButton();
  els.urlInput.focus();
}

function looksLikeUrl(text) {
  return /^https?:\/\/\S+\.\S+/i.test(text);
}

function formatCount(number) {
  return new Intl.NumberFormat(undefined, { notation: "compact" }).format(number);
}

function formatUploadDate(text) {
  if (!text || text.length !== 8) return "";
  const date = new Date(Number(text.slice(0, 4)), Number(text.slice(4, 6)) - 1, Number(text.slice(6, 8)));
  return date.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

function showPreview(info) {
  state.info = info;
  els.previewTitle.textContent = info.title;
  els.previewMeta.textContent = [
    info.uploader,
    formatDuration(info.duration),
    info.view_count ? `${formatCount(info.view_count)} views` : "",
    formatUploadDate(info.upload_date),
  ]
    .filter(Boolean)
    .join(" · ");

  const top = info.qualities[0];
  els.previewQuality.textContent = top
    ? `Available up to ${top.label}${info.qualities.length > 1 ? `, ${info.qualities.length} video qualities` : ""}`
    : "No video qualities listed. Audio formats still work.";

  if (info.thumbnail) {
    els.previewThumb.src = info.thumbnail;
    els.previewThumb.hidden = false;
  } else {
    els.previewThumb.hidden = true;
  }

  els.thumbSize.replaceChildren();
  for (const size of info.thumbnails) {
    const option = document.createElement("option");
    option.value = size.id;
    option.textContent = size.label;
    els.thumbSize.appendChild(option);
  }
  els.thumbTools.hidden = info.thumbnails.length === 0;
  els.preview.hidden = false;
  renderQualityOptions();
  renderSpec();
}

async function previewUrl({ quiet = false } = {}) {
  const url = els.urlInput.value.trim();
  if (!url) {
    if (!quiet) setStatus("Paste a video link first.", "error");
    els.urlInput.focus();
    return;
  }
  if (url === state.previewedUrl && state.info) return;
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
    if (els.urlInput.value.trim() !== url) return; // the link changed while we waited
    state.previewedUrl = url;
    showPreview(info);
    setStatus("");
  } catch (error) {
    if (els.urlInput.value.trim() === url) {
      resetPreview();
      setStatus(error.message, "error");
    }
  } finally {
    setBusy(false);
  }
}

/* Look up the link by itself once it has been pasted or typed. */
function onUrlInput() {
  updateClearButton();
  clearTimeout(state.previewTimer);
  const url = els.urlInput.value.trim();
  if (url !== state.previewedUrl) {
    state.info = null;
    els.preview.hidden = true;
    if (state.catalogue) {
      renderQualityOptions();
      renderSpec();
    }
  }
  if (looksLikeUrl(url) && !state.busy) {
    state.previewTimer = setTimeout(() => previewUrl({ quiet: true }), 700);
  }
}

async function downloadThumbnail() {
  const url = state.previewedUrl;
  if (!url || !els.thumbSize.value) return;
  els.thumbDownload.disabled = true;
  try {
    const response = await fetch("/api/thumbnail", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url,
        id: els.thumbSize.value,
        format: els.thumbFormat.value,
        square: els.thumbSquare.checked,
      }),
    });
    if (!response.ok) throw new Error(await errorMessage(response));
    const blob = await response.blob();
    const name = filenameFrom(response, `thumbnail.${els.thumbFormat.value}`);
    saveBlob(blob, name);
    setStatus(`Saved ${name} (${formatSize(blob.size)})`, "success");
  } catch (error) {
    setStatus(error.message || "The thumbnail could not be saved.", "error");
  } finally {
    els.thumbDownload.disabled = false;
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

/* ---------- playlist ---------- */

function selectedEntries() {
  if (!state.playlist) return [];
  const checked = new Set(
    [...els.playlistList.querySelectorAll("input:checked")].map((box) => Number(box.value)),
  );
  return state.playlist.entries.filter((entry) => checked.has(entry.index));
}

function updatePlaylistSelection() {
  const boxes = [...els.playlistList.querySelectorAll("input")];
  const chosen = boxes.filter((box) => box.checked).length;
  els.playlistAll.checked = chosen === boxes.length;
  els.playlistAll.indeterminate = chosen > 0 && chosen < boxes.length;
  els.playlistCount.textContent = `${chosen} of ${boxes.length} videos selected`;
  els.submitBtn.textContent = submitLabel();
  els.submitBtn.disabled = state.busy || chosen === 0;
}

function updateFolderHint() {
  const name = state.playlist ? state.playlist.title : "playlist name";
  const dir = state.catalogue ? state.catalogue.download_dir : "downloads";
  els.folderHint.textContent = els.optFolder.checked
    ? `Files are saved in ${dir}, in a folder named after the playlist (${name}).`
    : "Nothing is kept on disk. Download the ZIP when the job finishes.";
}

function renderPlaylist(playlist) {
  els.playlistTitle.textContent = playlist.title;
  els.playlistList.replaceChildren();
  for (const entry of playlist.entries) {
    const item = document.createElement("li");
    const label = document.createElement("label");
    label.className = "check";

    const box = document.createElement("input");
    box.type = "checkbox";
    box.value = entry.index;
    box.checked = true;

    const title = document.createElement("span");
    title.className = "pl-title";
    title.textContent = `${entry.index}. ${entry.title}`;
    title.title = entry.title;

    const time = document.createElement("span");
    time.className = "pl-time";
    time.textContent = entry.duration ? formatDuration(entry.duration) : "";

    label.append(box, title, time);
    item.appendChild(label);
    els.playlistList.appendChild(item);
  }
  els.playlistBox.hidden = false;
  updatePlaylistSelection();
  updateFolderHint();
}

async function loadPlaylist() {
  const url = els.playlistInput.value.trim();
  if (!url) {
    setStatus("Paste a playlist link first.", "error");
    els.playlistInput.focus();
    return;
  }
  setBusy(true);
  setStatus("Loading the playlist. Long playlists can take a moment...");
  try {
    const response = await fetch("/api/playlist/info", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    if (!response.ok) throw new Error(await errorMessage(response));
    state.playlist = await response.json();
    renderPlaylist(state.playlist);
    const limit = state.playlist.limit;
    setStatus(
      state.playlist.entries.length >= limit ? `Only the first ${limit} videos are listed.` : "",
    );
  } catch (error) {
    state.playlist = null;
    els.playlistBox.hidden = true;
    setStatus(error.message, "error");
  } finally {
    setBusy(false);
    updatePlaylistSelection();
  }
}

const STATE_TEXT = {
  queued: "Waiting",
  running: "Converting",
  done: "Done",
  failed: "Failed",
  skipped: "Skipped",
};

function renderJob(job) {
  const finished = job.status === "done" || job.status === "cancelled";
  const handled = job.items.filter((item) => ["done", "failed", "skipped"].includes(item.status));
  els.job.hidden = false;
  const running = job.items.find((item) => item.status === "running");
  const fraction = running && typeof running.percent === "number" ? running.percent / 100 : 0;
  const overall = finished ? 1 : (handled.length + fraction) / job.total;
  els.jobBar.style.width = `${overall * 100}%`;

  if (finished || !running) {
    els.jobDetail.textContent = "";
  } else {
    const parts = [describeProgress(running)];
    const elapsed = (Date.now() - state.jobStarted) / 1000;
    if (handled.length >= 1 && overall > 0) {
      parts.push(`${formatTimeLeft((elapsed / overall) * (1 - overall)).replace(" left", " left overall")}`);
    }
    els.jobDetail.textContent = parts.filter(Boolean).join(" \u00b7 ");
  }

  const failed = job.failed ? `, ${job.failed} failed` : "";
  els.jobSummary.textContent = finished
    ? `${job.status === "cancelled" ? "Stopped" : "Finished"}: ${job.done} of ${job.total} converted${failed}`
    : `Converting ${handled.length + 1 > job.total ? job.total : handled.length + 1} of ${job.total}${failed}`;
  els.jobCancel.hidden = finished;

  els.jobItems.replaceChildren();
  for (const item of job.items) {
    const row = document.createElement("li");
    row.className = `is-${item.status}`;
    const stateLabel = document.createElement("span");
    stateLabel.className = "state";
    stateLabel.textContent =
      item.status === "running" && typeof item.percent === "number"
        ? `${Math.floor(item.percent)}%`
        : STATE_TEXT[item.status] || item.status;
    const name = document.createElement("span");
    name.className = "name";
    name.textContent = item.filename || item.title;
    for (const text of [item.error, item.note]) {
      if (!text) continue;
      const reason = document.createElement("small");
      reason.textContent = text;
      name.appendChild(reason);
    }
    row.append(stateLabel, name);
    els.jobItems.appendChild(row);
  }

  els.jobActions.hidden = !(finished && (job.folder || job.zip_ready));
  els.jobOpen.hidden = !job.folder || !isThisComputer();
  els.jobZip.hidden = !job.zip_ready;
  if (job.zip_ready) els.jobZip.href = `/api/jobs/${job.id}/zip`;
}

/* The folder lives on the computer running MediaForge, which may not be this device. */
function isThisComputer() {
  return ["localhost", "127.0.0.1", "[::1]", "::1"].includes(location.hostname);
}

function stopPolling() {
  clearInterval(state.poller);
  state.poller = null;
}

async function pollJob() {
  try {
    const response = await fetch(`/api/jobs/${state.jobId}`);
    if (!response.ok) throw new Error(await errorMessage(response));
    const job = await response.json();
    if (state.jobKind === "single") {
      renderSingleJob(job);
      return;
    }
    renderJob(job);
    if (job.status === "done" || job.status === "cancelled") {
      stopPolling();
      setBusy(false);
      updatePlaylistSelection();
      if (job.folder) {
        const where = isThisComputer() ? "" : " (on the computer running MediaForge)";
        setStatus(`Saved to ${job.folder}${where}`, "success");
      }
      else if (job.zip_ready) setStatus("Your ZIP is ready. Use Download ZIP.", "success");
      else setStatus("No videos could be converted.", "error");
    }
  } catch (error) {
    stopPolling();
    setBusy(false);
    setStatus(error.message || "Lost contact with the server.", "error");
  }
}

async function startPlaylistJob() {
  const entries = selectedEntries();
  if (!state.playlist || entries.length === 0) throw new Error("Select at least one video.");
  if (!els.optFolder.checked && !els.optZip.checked) {
    throw new Error("Choose a folder, a ZIP, or both.");
  }
  const quality = els.qualityField.hidden ? "" : els.qualitySelect.value;
  const response = await fetch("/api/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title: state.playlist.title,
      items: entries.map(({ title, url }) => ({ title, url })),
      format: state.format,
      quality: quality || null,
      mute: isMuted(),
      save_to_folder: els.optFolder.checked,
      make_zip: els.optZip.checked,
    }),
  });
  if (!response.ok) throw new Error(await errorMessage(response));
  const job = await response.json();
  state.jobId = job.id;
  state.jobKind = "playlist";
  state.jobStarted = Date.now();
  renderJob(job);
  stopPolling();
  state.poller = setInterval(pollJob, 1000);
}

async function cancelJob() {
  if (!state.jobId) return;
  els.jobCancel.disabled = true;
  try {
    await fetch(`/api/jobs/${state.jobId}/cancel`, { method: "POST" });
    setStatus("Stopping after the current video...");
  } finally {
    els.jobCancel.disabled = false;
  }
}

async function openJobFolder() {
  try {
    const response = await fetch(`/api/jobs/${state.jobId}/open-folder`, { method: "POST" });
    if (!response.ok) throw new Error(await errorMessage(response));
  } catch (error) {
    setStatus(error.message, "error");
  }
}

/* ---------- convert ---------- */

/* ---------- single link or file: a background job with live progress ---------- */

function currentQuality() {
  return els.qualityField.hidden ? "" : els.qualitySelect.value;
}

async function startLinkJob() {
  const url = els.urlInput.value.trim();
  if (!url) throw new Error("Paste a video link first.");
  const response = await fetch("/api/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title: (state.info && state.info.title) || "Download",
      items: [{ title: (state.info && state.info.title) || url, url }],
      format: state.format,
      quality: currentQuality() || null,
      mute: isMuted(),
      save_to_folder: false,
      make_zip: false,
      deliver_to_browser: true,
    }),
  });
  if (!response.ok) throw new Error(await errorMessage(response));
  return response.json();
}

/* Upload with XMLHttpRequest because fetch cannot report upload progress. */
function startFileJob() {
  const file = els.fileInput.files[0];
  if (!file) return Promise.reject(new Error("Choose a file first."));
  const limitMb = state.catalogue.limits.max_upload_mb;
  if (file.size > limitMb * 1024 * 1024) {
    return Promise.reject(new Error(`That file is larger than the ${limitMb} MB limit.`));
  }
  const data = new FormData();
  data.append("file", file);
  data.append("format", state.format);
  if (currentQuality()) data.append("quality", currentQuality());
  data.append("mute", String(isMuted()));

  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    const started = Date.now();
    state.upload = request;
    request.open("POST", "/api/jobs/upload");
    request.upload.onprogress = (event) => {
      if (!event.lengthComputable) return;
      const seconds = Math.max(0.2, (Date.now() - started) / 1000);
      const speed = event.loaded / seconds;
      showProgress({
        phase: "uploading",
        percent: Math.min(99, (event.loaded / event.total) * 100),
        speed,
        eta: (event.total - event.loaded) / speed,
      });
    };
    request.onload = () => {
      state.upload = null;
      let body = {};
      try { body = JSON.parse(request.responseText); } catch (_) { /* not JSON */ }
      if (request.status >= 200 && request.status < 300) resolve(body);
      else reject(new Error(typeof body.detail === "string" ? body.detail : `The server returned an error (${request.status}).`));
    };
    request.onerror = () => {
      state.upload = null;
      reject(new Error("The upload failed. Check that MediaForge is still running."));
    };
    request.onabort = () => {
      state.upload = null;
      reject(new Error("Stopped."));
    };
    request.send(data);
  });
}

function showProgress(item) {
  setMeter(typeof item.percent === "number" ? item.percent : null);
  els.progressText.textContent = describeProgress(item);
}

function finishSingle(kind, message) {
  stopPolling();
  state.jobId = null;
  setBusy(false);
  setStatus(message, kind);
}

function renderSingleJob(job) {
  const item = job.items[0];
  if (job.status === "queued" || job.status === "running" || job.status === "uploading") {
    showProgress(item.status === "queued" ? { phase: "queued" } : item);
    return;
  }
  if (item.status === "done" && item.downloadable) {
    const link = document.createElement("a");
    link.href = `/api/jobs/${job.id}/items/${item.index}/file`;
    link.download = item.filename || "";
    document.body.appendChild(link);
    link.click();
    link.remove();
    const note = item.note ? ` ${item.note}` : "";
    finishSingle("success", `Done: ${item.filename}.${note}`);
  } else if (item.status === "failed") {
    finishSingle("error", item.error || "The conversion failed.");
  } else {
    finishSingle("", "Stopped.");
  }
}

async function runSingleJob() {
  setBusy(true, { showProgress: true });
  setStatus("");
  state.jobKind = "single";
  state.jobStarted = Date.now();
  try {
    const job = state.mode === "url" ? await startLinkJob() : await startFileJob();
    state.jobId = job.id;
    renderSingleJob(job);
    if (state.jobId) {
      stopPolling();
      state.poller = setInterval(pollJob, 700);
    }
  } catch (error) {
    stopPolling();
    state.jobId = null;
    setBusy(false);
    setStatus(error.message === "Stopped." ? "Stopped." : error.message || "Something went wrong.", error.message === "Stopped." ? "" : "error");
  }
}

async function cancelSingleJob() {
  if (state.upload) {
    state.upload.abort();
    return;
  }
  if (!state.jobId) return;
  els.progressCancel.disabled = true;
  try {
    await fetch(`/api/jobs/${state.jobId}/cancel`, { method: "POST" });
    els.progressText.textContent = "Stopping...";
  } finally {
    els.progressCancel.disabled = false;
  }
}

async function onSubmit(event) {
  event.preventDefault();
  if (state.busy || !state.catalogue) return;

  if (state.mode === "playlist") {
    setBusy(true);
    setStatus("");
    els.submitBtn.textContent = "Working through the playlist...";
    try {
      await startPlaylistJob();
    } catch (error) {
      setBusy(false);
      updatePlaylistSelection();
      setStatus(error.message || "Something went wrong.", "error");
    }
    return;
  }

  await runSingleJob();
}

/* ---------- theme: System, Light or Dark ---------- */

const THEME_KEY = "mediaforge-theme";

function savedTheme() {
  try {
    const value = localStorage.getItem(THEME_KEY);
    return value === "light" || value === "dark" ? value : "system";
  } catch (_) {
    return "system";
  }
}

function applyTheme(choice) {
  const root = document.documentElement;
  if (choice === "system") root.removeAttribute("data-theme");
  else root.dataset.theme = choice;
  for (const button of els.themeSwitch.querySelectorAll("button")) {
    button.setAttribute("aria-checked", String(button.dataset.themeChoice === choice));
  }
}

function chooseTheme(choice) {
  applyTheme(choice);
  try {
    if (choice === "system") localStorage.removeItem(THEME_KEY);
    else localStorage.setItem(THEME_KEY, choice);
  } catch (_) { /* the choice just will not be remembered */ }
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
els.tabPlaylist.addEventListener("click", () => selectTab("playlist"));
for (const tab of [els.tabUrl, els.tabFile, els.tabPlaylist]) tab.addEventListener("keydown", onTabKeys);

els.playlistLoad.addEventListener("click", loadPlaylist);
els.playlistInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    loadPlaylist();
  }
});
els.playlistAll.addEventListener("change", () => {
  for (const box of els.playlistList.querySelectorAll("input")) box.checked = els.playlistAll.checked;
  updatePlaylistSelection();
});
els.playlistList.addEventListener("change", updatePlaylistSelection);
els.optFolder.addEventListener("change", updateFolderHint);
els.jobCancel.addEventListener("click", cancelJob);
els.progressCancel.addEventListener("click", cancelSingleJob);
applyTheme(savedTheme());
els.themeSwitch.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-theme-choice]");
  if (button) chooseTheme(button.dataset.themeChoice);
});
els.jobOpen.addEventListener("click", openJobFolder);

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

els.urlInput.addEventListener("input", onUrlInput);
els.urlInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    clearTimeout(state.previewTimer);
    previewUrl();
  }
});
els.thumbDownload.addEventListener("click", downloadThumbnail);
els.optMute.addEventListener("change", renderSpec);
els.clearBtn.addEventListener("click", clearUrl);
els.previewBtn.addEventListener("click", () => previewUrl());
els.form.addEventListener("submit", onSubmit);

buildWave();
setupDropzone();
loadFormats();
checkSetup();
