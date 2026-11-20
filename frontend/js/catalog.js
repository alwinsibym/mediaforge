/* Formats, quality and the details panel. */

import { els } from "./dom.js";
import { setStatus } from "./errors.js";
import { updateExtras } from "./extras.js";
import { formatSize } from "./format.js";
import { setupTweaks, updateTweaks } from "./tweaks.js";
import { state } from "./state.js";

/* What each output format is made of, for the details panel. */
export const FORMAT_INFO = {
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

export function isPreset() {
  return state.catalogue.video.some((f) => f.id === state.format && f.preset);
}

export function renderQualityOptions() {
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

export function renderSpec() {
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

export function isMuted() {
  return state.kind === "video" && els.optMute.checked;
}

function highResolutionNote() {
  if (state.kind !== "video" || isPreset() || els.qualityField.hidden) return "";
  const quality = els.qualitySelect.value;
  const height = quality === "best" ? 9999 : heightOf(quality);
  if (height <= 1080 || state.format === "webm") return "";
  return "Above 1080p, YouTube offers VP9 and AV1 video instead of H.264. MKV or WebM plays these most reliably, and MP4 may not play on older devices.";
}

export function selectKind(kind, format) {
  state.kind = kind;
  state.format = format || (kind === "audio" ? "mp3" : "mp4");
  for (const input of els.kindInputs) input.checked = input.value === kind;
  renderChips();
  renderQualityOptions();
  renderSpec();
  updateExtras();
  updateTweaks();
}

export async function loadFormats() {
  try {
    const response = await fetch("/api/formats");
    if (!response.ok) throw new Error();
    state.catalogue = await response.json();
  } catch (_) {
    setStatus("Can't reach the MediaForge server. Is it running?", "error");
    els.submitBtn.disabled = true;
    return;
  }
  setupTweaks();
  selectKind("audio");
}

export function currentQuality() {
  return els.qualityField.hidden ? "" : els.qualitySelect.value;
}
