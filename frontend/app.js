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
  jobRetry: $("job-retry"),
  jobNotice: $("job-notice"),
  extras: $("extras"),
  extraNormalize: $("extra-normalize"),
  optNormalize: $("opt-normalize"),
  extraSponsor: $("extra-sponsor"),
  optSponsor: $("opt-sponsor"),
  extraSubs: $("extra-subs"),
  optSubs: $("opt-subs"),
  subsLangsField: $("subs-langs-field"),
  subsLangs: $("subs-langs"),
  extraTrim: $("extra-trim"),
  trimStart: $("trim-start"),
  trimEnd: $("trim-end"),
  extraChapters: $("extra-chapters"),
  optChapters: $("opt-chapters"),
  pending: $("pending"),
  pendingList: $("pending-list"),
  historyBtn: $("history-btn"),
  settingsBtn: $("settings-btn"),
  settingsDialog: $("settings-dialog"),
  settingsForm: $("settings-form"),
  setBrowser: $("set-browser"),
  setCookies: $("set-cookies"),
  setParallel: $("set-parallel"),
  setAria2c: $("set-aria2c"),
  ariaHint: $("aria-hint"),
  ytdlpVersion: $("ytdlp-version"),
  ytdlpUpdate: $("ytdlp-update"),
  ytdlpResult: $("ytdlp-result"),
  settingsStatus: $("settings-status"),
  settingsClose: $("settings-close"),
  historyDialog: $("history-dialog"),
  historyList: $("history-list"),
  historyEmpty: $("history-empty"),
  historyClear: $("history-clear"),
  historyClose: $("history-close"),
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
  failedItems: [],
  lastBody: null,
};

const TABS = {
  url: { tab: "tab-url", panel: "panel-url" },
  file: { tab: "tab-file", panel: "panel-file" },
  playlist: { tab: "tab-playlist", panel: "panel-playlist" },
};

/* What each output format is made of, for the details panel. */
const FORMAT_INFO = {
  mp3: { label: "MP3", container: "MP3", codec: "MP3 (LAME)" },
  m4a: { label: "M4A", container: "M4A", codec: "AAC (copied as is when possible)" },
  aac: { label: "AAC", container: "AAC stream", codec: "AAC" },
  wav: { label: "WAV", container: "WAV", codec: "PCM, 16-bit" },
  flac: { label: "FLAC", container: "FLAC", codec: "FLAC, lossless" },
  ogg: { label: "OGG", container: "OGG", codec: "Vorbis" },
  opus: { label: "Opus", container: "Opus", codec: "Opus (copied as is when possible)" },
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

function setStatus(message, kind = "", info = null) {
  els.status.className = "status" + (kind ? ` is-${kind}` : "");
  if (info) {
    els.status.replaceChildren(buildErrorCard(info, message));
    els.status.classList.add("has-card");
  } else {
    els.status.textContent = message;
  }
}

/* Shows a caught error. Errors from the server carry a full explanation in `.info`. */
function setProblem(error, fallback = "Something went wrong.") {
  setStatus((error && error.message) || fallback, "error", error && error.info);
}

function listBlock(heading, lines, ordered) {
  const wrap = document.createElement("div");
  wrap.className = "err-block";
  const title = document.createElement("h4");
  title.textContent = heading;
  const list = document.createElement(ordered ? "ol" : "ul");
  for (const line of lines) {
    const li = document.createElement("li");
    li.textContent = line;
    list.appendChild(li);
  }
  wrap.append(title, list);
  return wrap;
}

/* A short title and code first; the longer explanation opens on request. */
function buildErrorCard(info, message) {
  const card = document.createElement("div");
  card.className = "err-card";
  const head = document.createElement("div");
  head.className = "err-head";
  const title = document.createElement("strong");
  title.textContent = info.title;
  const code = document.createElement("code");
  code.className = "err-code";
  code.textContent = info.code;
  head.append(title, code);
  const summary = document.createElement("p");
  summary.className = "err-summary";
  summary.textContent = info.summary;
  card.append(head, summary);
  if (message && message !== info.summary && message !== info.title && message !== info.technical) {
    const detail = document.createElement("p");
    detail.className = "err-message";
    detail.textContent = message;
    card.appendChild(detail);
  }
  const more = document.createElement("details");
  more.className = "err-more";
  const toggle = document.createElement("summary");
  toggle.textContent = "What happened and what to do";
  more.appendChild(toggle);
  const what = document.createElement("p");
  what.textContent = info.what;
  more.appendChild(what);
  if (info.why && info.why.length) more.appendChild(listBlock("Why this can happen", info.why, false));
  if (info.fix && info.fix.length) more.appendChild(listBlock("What to do now", info.fix, true));
  if (info.technical) {
    const tech = document.createElement("pre");
    tech.className = "err-tech";
    tech.textContent = info.technical;
    const label = document.createElement("h4");
    label.textContent = "Technical details";
    more.append(label, tech);
  }
  card.appendChild(more);
  return card;
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
  waiting: "The site asked for a sign-in check. Waiting before trying again",
  offline: "No internet connection. Waiting for it to come back",
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

async function problemFrom(response) {
  let message = `The server returned an error (${response.status}).`;
  let info = null;
  try {
    const body = await response.json();
    if (typeof body.detail === "string") message = body.detail;
    else if (Array.isArray(body.detail)) message = "Please check your input and try again.";
    if (body.error && body.error.code) info = body.error;
  } catch (_) { /* not JSON */ }
  const error = new Error(message);
  error.info = info;
  return error;
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

function selectKind(kind, format) {
  state.kind = kind;
  state.format = format || (kind === "audio" ? "mp3" : "mp4");
  for (const input of els.kindInputs) input.checked = input.value === kind;
  renderChips();
  renderQualityOptions();
  renderSpec();
  updateExtras();
}

/* ---------- more options ---------- */

/* Show only the extras that make sense for this tab and format. */
function updateExtras() {
  const link = state.mode === "url";
  const video = state.kind === "video" && !isPreset();
  els.extraSponsor.hidden = state.mode === "file";
  els.extraSubs.hidden = !(video && state.mode !== "file");
  els.subsLangsField.hidden = els.extraSubs.hidden || !els.optSubs.checked;
  els.extraTrim.hidden = !link;
  els.extraChapters.hidden = !link || (state.kind === "video" && isPreset());
}

/* What the person asked for in "More options", as the server expects it. */
function collectOptions() {
  const options = { normalize: els.optNormalize.checked };
  if (!els.extraSponsor.hidden) options.sponsorblock = els.optSponsor.checked;
  if (!els.extraSubs.hidden && els.optSubs.checked) {
    options.subtitles = true;
    options.subtitle_langs = els.subsLangs.value.trim() || "en";
  }
  if (!els.extraTrim.hidden) {
    options.trim_start = els.trimStart.value.trim();
    options.trim_end = els.trimEnd.value.trim();
  }
  if (!els.extraChapters.hidden) options.split_chapters = els.optChapters.checked;
  return options;
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
  updateExtras();
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
    if (!response.ok) throw await problemFrom(response);
    const info = await response.json();
    if (els.urlInput.value.trim() !== url) return; // the link changed while we waited
    state.previewedUrl = url;
    showPreview(info);
    setStatus("");
  } catch (error) {
    if (els.urlInput.value.trim() === url) {
      resetPreview();
      setProblem(error);
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
    if (!response.ok) throw await problemFrom(response);
    const blob = await response.blob();
    const name = filenameFrom(response, `thumbnail.${els.thumbFormat.value}`);
    saveBlob(blob, name);
    setStatus(`Saved ${name} (${formatSize(blob.size)})`, "success");
  } catch (error) {
    setProblem(error, "The thumbnail could not be saved.");
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
    if (!response.ok) throw await problemFrom(response);
    state.playlist = await response.json();
    renderPlaylist(state.playlist);
    const limit = state.playlist.limit;
    setStatus(
      state.playlist.entries.length >= limit ? `Only the first ${limit} videos are listed.` : "",
    );
  } catch (error) {
    state.playlist = null;
    els.playlistBox.hidden = true;
    setProblem(error);
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
  const active = job.items.filter((item) => item.status === "running");
  const fraction = active.reduce(
    (sum, item) => sum + (typeof item.percent === "number" ? item.percent / 100 : 0),
    0,
  );
  const overall = finished ? 1 : Math.min(1, (handled.length + fraction) / job.total);
  els.jobBar.style.width = `${overall * 100}%`;

  if (finished || active.length === 0) {
    els.jobDetail.textContent = "";
  } else {
    const parts = [];
    if (active.length === 1) {
      parts.push(describeProgress(active[0]));
    } else {
      const speed = active.reduce((sum, item) => sum + (item.speed || 0), 0);
      parts.push(`${active.length} at a time`, formatSpeed(speed));
    }
    const elapsed = (Date.now() - state.jobStarted) / 1000;
    if (handled.length >= 1 && overall > 0) {
      parts.push(formatTimeLeft((elapsed / overall) * (1 - overall)).replace(" left", " left overall"));
    }
    els.jobDetail.textContent = parts.filter(Boolean).join(" \u00b7 ");
  }

  state.failedItems = finished
    ? job.items
        .filter((item) => ["failed", "skipped"].includes(item.status) && item.url)
        .map((item) => ({ title: item.title, url: item.url, number: item.number }))
    : [];
  els.jobRetry.hidden = state.failedItems.length === 0;
  els.jobRetry.textContent = `Retry ${state.failedItems.length}`;
  els.jobNotice.hidden = !(finished && job.blocked);
  if (job.blocked) {
    els.jobNotice.textContent =
      job.blocked_reason === "network"
        ? "MediaForge could not reach the site, so it stopped instead of failing every video. " +
          "Check your internet connection, then choose Retry. The videos already saved are kept."
        : "The site kept asking for a sign-in check, so MediaForge stopped before it got worse. " +
          "Open Settings and choose the browser where you are signed in, wait a few minutes, " +
          "then choose Retry. The videos already saved are kept.";
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
    if (item.status === "running" && item.phase === "waiting") stateLabel.textContent = "Paused";
    else if (item.status === "running" && typeof item.percent === "number") {
      stateLabel.textContent = `${Math.floor(item.percent)}%`;
    } else stateLabel.textContent = STATE_TEXT[item.status] || item.status;
    const name = document.createElement("span");
    name.className = "name";
    name.textContent = item.filename || item.title;
    for (const text of [item.error, item.note]) {
      if (!text) continue;
      const reason = document.createElement("small");
      reason.textContent = text;
      name.appendChild(reason);
    }
    if (item.error_info) {
      const info = item.error_info;
      const more = document.createElement("details");
      more.className = "err-row";
      const toggle = document.createElement("summary");
      toggle.textContent = `${info.title} (${info.code})`;
      more.appendChild(toggle);
      const what = document.createElement("p");
      what.textContent = info.what;
      more.appendChild(what);
      if (info.fix && info.fix.length) more.appendChild(listBlock("What to do now", info.fix, true));
      name.appendChild(more);
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
    if (!response.ok) throw await problemFrom(response);
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
      loadPending();
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
    setProblem(error, "Lost contact with the server.");
  }
}

async function startPlaylistJob({ retry = false } = {}) {
  let body;
  if (retry) {
    if (!state.lastBody || state.failedItems.length === 0) throw new Error("Nothing to retry.");
    body = { ...state.lastBody, items: state.failedItems, continue_job: state.jobId };
  } else {
    const entries = selectedEntries();
    if (!state.playlist || entries.length === 0) throw new Error("Select at least one video.");
    if (!els.optFolder.checked && !els.optZip.checked) {
      throw new Error("Choose a folder, a ZIP, or both.");
    }
    body = {
      title: state.playlist.title,
      items: entries.map(({ title, url }) => ({ title, url })),
      format: state.format,
      quality: currentQuality() || null,
      mute: isMuted(),
      save_to_folder: els.optFolder.checked,
      make_zip: els.optZip.checked,
      options: collectOptions(),
    };
  }
  const response = await fetch("/api/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw await problemFrom(response);
  const job = await response.json();
  state.lastBody = { ...body, continue_job: undefined };
  state.jobId = job.id;
  state.jobKind = "playlist";
  state.jobStarted = Date.now();
  renderJob(job);
  stopPolling();
  state.poller = setInterval(pollJob, 1000);
}

async function retryFailed() {
  if (state.busy) return;
  setBusy(true);
  setStatus("");
  els.submitBtn.textContent = "Working through the playlist...";
  try {
    await startPlaylistJob({ retry: true });
  } catch (error) {
    setBusy(false);
    updatePlaylistSelection();
    setProblem(error, "Something went wrong.");
  }
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
    if (!response.ok) throw await problemFrom(response);
  } catch (error) {
    setProblem(error);
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
      options: collectOptions(),
    }),
  });
  if (!response.ok) throw await problemFrom(response);
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
  data.append("normalize", String(els.optNormalize.checked));

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

function finishSingle(kind, message, info = null) {
  stopPolling();
  state.jobId = null;
  setBusy(false);
  setStatus(message, kind, info);
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
    finishSingle("error", item.error || "The conversion failed.", item.error_info);
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
      setProblem(error, "Something went wrong.");
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

/* ---------- settings and history (this computer only) ---------- */

function fillSelect(select, options, selected) {
  select.replaceChildren();
  for (const [value, label] of options) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    option.selected = String(value) === String(selected);
    select.appendChild(option);
  }
}

async function openSettings() {
  els.settingsStatus.textContent = "";
  els.ytdlpResult.textContent = "";
  try {
    const [settingsResponse, healthResponse] = await Promise.all([
      fetch("/api/settings"),
      fetch("/api/health"),
    ]);
    if (!settingsResponse.ok) throw await problemFrom(settingsResponse);
    const saved = await settingsResponse.json();
    const health = await healthResponse.json();

    fillSelect(
      els.setBrowser,
      [["", "Nothing"], ...saved.cookie_browsers.map((name) => [name, name[0].toUpperCase() + name.slice(1)])],
      saved.cookies_browser,
    );
    els.setCookies.value = saved.cookies_file;
    const counts = Array.from({ length: saved.max_parallel }, (_, i) => [i + 1, String(i + 1)]);
    fillSelect(els.setParallel, counts, saved.parallel);
    els.setAria2c.checked = saved.aria2c && saved.aria2c_installed;
    els.setAria2c.disabled = !saved.aria2c_installed;
    els.ariaHint.textContent = saved.aria2c_installed
      ? "aria2c was found. The progress bar cannot show a percentage while it is used."
      : "aria2c is not installed. On Windows: winget install aria2.aria2, then open this window again.";
    els.ytdlpVersion.textContent = health.yt_dlp ? `Installed: yt-dlp ${health.yt_dlp}.` : "";
    els.settingsDialog.showModal();
  } catch (error) {
    setProblem(error, "Settings could not be opened.");
  }
}

async function saveSettings(event) {
  event.preventDefault();
  els.settingsStatus.className = "status";
  els.settingsStatus.textContent = "";
  try {
    const response = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        cookies_browser: els.setBrowser.value,
        cookies_file: els.setCookies.value.trim(),
        parallel: Number(els.setParallel.value),
        aria2c: els.setAria2c.checked,
      }),
    });
    if (!response.ok) throw await problemFrom(response);
    els.settingsDialog.close();
    setStatus("Settings saved.", "success");
  } catch (error) {
    els.settingsStatus.className = "status is-error";
    els.settingsStatus.textContent = error.message || "The settings could not be saved.";
  }
}

async function updateYtdlp() {
  els.ytdlpUpdate.disabled = true;
  els.ytdlpResult.textContent = "Updating. This can take a minute...";
  try {
    const response = await fetch("/api/update-ytdlp", { method: "POST" });
    if (!response.ok) throw await problemFrom(response);
    const result = await response.json();
    els.ytdlpResult.textContent = result.changed
      ? `Updated from ${result.before} to ${result.after}. Close MediaForge and start it again to use the new version.`
      : `Already up to date (${result.after}).`;
    els.ytdlpVersion.textContent = `Installed: yt-dlp ${result.after}.`;
  } catch (error) {
    els.ytdlpResult.textContent = error.message || "The update failed.";
  } finally {
    els.ytdlpUpdate.disabled = false;
  }
}

function useAgain(entry) {
  els.historyDialog.close();
  selectTab("url");
  const kind = state.catalogue.audio.some((f) => f.id === entry.format) ? "audio" : "video";
  selectKind(kind, entry.format);
  if ([...els.qualitySelect.options].some((o) => o.value === entry.quality)) {
    els.qualitySelect.value = entry.quality;
    renderSpec();
  }
  els.urlInput.value = entry.url;
  updateClearButton();
  previewUrl();
}

async function openHistory() {
  try {
    const response = await fetch("/api/history");
    if (!response.ok) throw await problemFrom(response);
    renderHistory((await response.json()).items);
    els.historyDialog.showModal();
  } catch (error) {
    setProblem(error, "History could not be opened.");
  }
}

function renderHistory(items) {
  els.historyList.replaceChildren();
  els.historyEmpty.hidden = items.length > 0;
  els.historyClear.hidden = items.length === 0;
  for (const entry of items) {
    const row = document.createElement("li");
    const name = document.createElement("span");
    name.className = "name";
    name.textContent = entry.title;
    const meta = document.createElement("small");
    const label = FORMAT_INFO[entry.format]?.label || entry.format.toUpperCase();
    meta.textContent = `${label} \u00b7 ${new Date(entry.when * 1000).toLocaleString()}`;
    name.appendChild(meta);
    const again = document.createElement("button");
    again.type = "button";
    again.className = "btn btn-quiet";
    again.textContent = "Use again";
    again.addEventListener("click", () => useAgain(entry));
    row.append(name, again);
    els.historyList.appendChild(row);
  }
}

/* ---------- unfinished downloads ---------- */

async function loadPending() {
  try {
    const response = await fetch("/api/pending");
    if (!response.ok) return;
    renderPending((await response.json()).items);
  } catch (_) {
    /* the list is only a convenience */
  }
}

function renderPending(items) {
  els.pendingList.replaceChildren();
  els.pending.hidden = items.length === 0;
  for (const entry of items) {
    const row = document.createElement("li");
    const name = document.createElement("span");
    name.className = "name";
    name.textContent = entry.title;
    const left = document.createElement("small");
    left.textContent = `${entry.left} video${entry.left === 1 ? "" : "s"} left`;
    name.appendChild(left);

    const resume = document.createElement("button");
    resume.type = "button";
    resume.className = "btn btn-primary";
    resume.textContent = "Resume";
    resume.addEventListener("click", () => resumePending(entry.id));
    const discard = document.createElement("button");
    discard.type = "button";
    discard.className = "btn btn-quiet";
    discard.textContent = "Remove";
    discard.addEventListener("click", async () => {
      const response = await fetch(`/api/pending/${entry.id}`, { method: "DELETE" });
      if (response.ok) renderPending((await response.json()).items);
    });
    const actions = document.createElement("span");
    actions.className = "actions";
    actions.append(resume, discard);
    row.append(name, actions);
    els.pendingList.appendChild(row);
  }
}

async function resumePending(id) {
  if (state.busy) {
    setStatus("Wait for the current download to finish, then resume.", "error");
    return;
  }
  setBusy(true);
  setStatus("");
  els.submitBtn.textContent = "Working through the playlist...";
  try {
    const response = await fetch(`/api/pending/${id}/resume`, { method: "POST" });
    if (!response.ok) throw await problemFrom(response);
    const { request, ...job } = await response.json();
    state.lastBody = request;
    state.jobId = job.id;
    state.jobKind = "playlist";
    state.jobStarted = Date.now();
    els.pending.hidden = true;
    renderJob(job);
    stopPolling();
    state.poller = setInterval(pollJob, 1000);
  } catch (error) {
    setBusy(false);
    updatePlaylistSelection();
    setProblem(error, "Something went wrong.");
  }
}

async function clearHistory() {
  const response = await fetch("/api/history", { method: "DELETE" });
  if (response.ok) renderHistory([]);
}

/* Settings and history belong to the person at the computer running MediaForge. */
async function revealLocalTools() {
  try {
    const response = await fetch("/api/settings");
    if (!response.ok) return;
  } catch (_) {
    return;
  }
  els.historyBtn.hidden = false;
  els.settingsBtn.hidden = false;
  loadPending();
}

function closeOnBackdrop(dialog) {
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });
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
els.jobRetry.addEventListener("click", retryFailed);
els.settingsBtn.addEventListener("click", openSettings);
els.historyBtn.addEventListener("click", openHistory);
els.settingsForm.addEventListener("submit", saveSettings);
els.settingsClose.addEventListener("click", () => els.settingsDialog.close());
els.ytdlpUpdate.addEventListener("click", updateYtdlp);
els.historyClose.addEventListener("click", () => els.historyDialog.close());
els.historyClear.addEventListener("click", clearHistory);
closeOnBackdrop(els.settingsDialog);
closeOnBackdrop(els.historyDialog);
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
  updateExtras();
});
els.qualitySelect.addEventListener("change", renderSpec);
els.optSubs.addEventListener("change", updateExtras);

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
revealLocalTools();
