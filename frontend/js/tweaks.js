/* The Tweaks section on the File tab: what to change about the file, and the file info panel. */

import { $, els } from "./dom.js";
import { setStatus } from "./errors.js";
import { formatDuration, formatSize } from "./format.js";
import { state } from "./state.js";

const t = {
  details: $("tweaks"),
  infoBtn: $("tw-info-btn"),
  info: $("file-info"),
  codecField: $("tw-codec-field"),
  codec: $("tw-codec"),
  resizeField: $("tw-resize-field"),
  resize: $("tw-resize"),
  targetField: $("tw-target-field"),
  target: $("tw-target"),
  sound: $("tw-sound"),
  volume: $("tw-volume"),
  fadeIn: $("tw-fade-in"),
  fadeOut: $("tw-fade-out"),
  effect: $("tw-effect"),
  audioField: $("tw-audio-field"),
  audioFile: $("tw-audio-file"),
  coverField: $("tw-cover-field"),
  coverFile: $("tw-cover-file"),
  coverPreview: $("tw-cover-preview"),
  subsGroup: $("tw-subs-group"),
  subsFile: $("tw-subs-file"),
  subsMode: $("tw-subs-mode"),
  start: $("tw-start"),
  end: $("tw-end"),
  animatedGroup: $("tw-animated-group"),
  animated: $("tw-animated"),
  widthField: $("tw-width-field"),
  width: $("tw-width"),
  meta: $("tw-meta"),
  note: $("tw-note"),
};

const RESIZE_LABELS = { 360: "360p", 480: "480p", 720: "720p (HD)", 1080: "1080p (Full HD)", 1440: "1440p (2K)", 2160: "2160p (4K)" };

function fill(select, items) {
  for (const [value, label] of items) select.append(new Option(label, value));
}

/* Fill the lists once the server's catalogue has arrived. */
export function setupTweaks() {
  const tweaks = state.catalogue?.tweaks;
  if (!tweaks) return;
  const caps = tweaks.capabilities;
  fill(t.codec, tweaks.video_codecs.map((c) => [c.id, caps.video_codecs[c.id] ? c.label : `${c.label} - not available here`]));
  [...t.codec.options].forEach((o) => { if (o.text.endsWith("not available here")) o.disabled = true; });
  fill(t.resize, tweaks.resize_heights.map((h) => [String(h), RESIZE_LABELS[h] || `${h}p`]));
  fill(t.effect, tweaks.effects.map((e) => [e.id, caps.effects[e.id] ? e.label : `${e.label} - not available here`]));
  [...t.effect.options].forEach((o) => { if (o.text.endsWith("not available here")) o.disabled = true; });
  fill(t.width, tweaks.animated_widths.map((w) => [String(w), `${w} px wide`]));
  t.width.value = "480";
  if (!caps.animated.gif) t.animated.querySelector('[value="gif"]').disabled = true;
  if (!caps.animated.webp) t.animated.querySelector('[value="webp"]').disabled = true;
  if (!caps.subtitles_burn) t.subsMode.querySelector('[value="burn"]').disabled = true;
  updateTweaks();
}

/* Show only the tweaks that make sense for the chosen output. */
export function updateTweaks() {
  const preset = state.format.startsWith("sony_");
  const video = state.kind === "video" && !preset;
  const audio = state.kind === "audio";
  const animated = Boolean(t.animated.value);
  const codecs = state.catalogue?.tweaks?.video_codecs || [];
  const allowed = new Set(codecs.filter((c) => c.containers.includes(state.format)).map((c) => c.id));
  [...t.codec.options].forEach((o) => {
    if (o.value && !o.text.endsWith("not available here")) o.disabled = !allowed.has(o.value);
  });
  if (t.codec.value && !allowed.has(t.codec.value)) t.codec.value = "";

  t.details.hidden = preset || state.mode !== "file";
  t.codecField.hidden = !video || animated;
  t.resizeField.hidden = !(video || animated);
  t.targetField.hidden = audio && ["wav", "flac"].includes(state.format) ? true : animated;
  t.audioField.hidden = !video || animated;
  t.subsGroup.hidden = !video || animated;
  const coverFormats = state.catalogue?.tweaks?.cover_formats || [];
  t.coverField.hidden = animated || !coverFormats.includes(state.format);
  t.animatedGroup.hidden = !video;
  t.widthField.hidden = !animated;
  t.sound.hidden = animated;
  if (!video && t.animated.value) t.animated.value = "";
  t.audioFile.disabled = els.optMute.checked;
  t.subsMode.hidden = !t.subsFile.files.length;
  t.infoBtn.disabled = !els.fileInput.files.length;
  const note = animated ? "The result is a picture without sound, so the format above is ignored." : "";
  t.note.textContent = note;
  t.note.hidden = !note;
}

function numberOrEmpty(input) {
  return input.value.trim();
}

/* What the person chose, as the server expects it: a JSON string and two optional files. */
export function collectTweaks() {
  if (state.format.startsWith("sony_")) return { options: "", audio: null, subtitles: null, cover: null };
  const o = {};
  const add = (key, value) => { if (value !== "" && value != null) o[key] = value; };
  const video = state.kind === "video";
  if (video) {
    add("video_codec", t.codecField.hidden ? "" : t.codec.value);
    add("resize", t.resizeField.hidden ? "" : t.resize.value);
    add("animated", t.animated.value);
    if (t.animated.value) add("animated_width", t.width.value);
  }
  if (!t.targetField.hidden) add("target_mb", numberOrEmpty(t.target));
  if (!t.sound.hidden) {
    const volume = numberOrEmpty(t.volume);
    if (volume && volume !== "100") o.volume = volume;
    add("fade_in", numberOrEmpty(t.fadeIn));
    add("fade_out", numberOrEmpty(t.fadeOut));
    add("effect", t.effect.value);
  }
  add("start", numberOrEmpty(t.start));
  add("end", numberOrEmpty(t.end));
  if (t.meta.checked) o.strip_metadata = true;
  const subs = !t.subsGroup.hidden && t.subsFile.files[0] ? t.subsFile.files[0] : null;
  if (subs) o.subtitles = document.querySelector('input[name="tw-subs"]:checked').value;
  const audio = !t.audioField.hidden && !t.audioFile.disabled && t.audioFile.files[0] ? t.audioFile.files[0] : null;
  if (audio) o.replace_audio = true;
  const cover = !t.coverField.hidden && t.coverFile.files[0] ? t.coverFile.files[0] : null;
  return { options: Object.keys(o).length ? JSON.stringify(o) : "", audio, subtitles: subs, cover };
}

function row(label, value) {
  const div = document.createElement("div");
  div.className = "info-row";
  const dt = document.createElement("dt");
  dt.textContent = label;
  const dd = document.createElement("dd");
  dd.textContent = value;
  div.append(dt, dd);
  return div;
}

function describeStream(s) {
  const bits = [s.codec.toUpperCase()];
  if (s.width) bits.push(`${s.width} x ${s.height}`);
  if (s.fps) bits.push(`${Math.round(s.fps)} fps`);
  if (s.sample_rate) bits.push(`${s.sample_rate / 1000} kHz`);
  if (s.channels) bits.push(s.channels);
  if (s.bitrate_kbps) bits.push(`${s.bitrate_kbps} kbps`);
  if (s.language) bits.push(s.language);
  return bits.join(", ");
}

/* Ask the server what is inside the chosen file. */
export async function showFileInfo() {
  const file = els.fileInput.files[0];
  if (!file) return;
  t.infoBtn.disabled = true;
  t.info.hidden = false;
  t.info.textContent = "Reading the file...";
  try {
    const data = new FormData();
    data.append("file", file);
    const response = await fetch("/api/probe", { method: "POST", body: data });
    if (!response.ok) throw new Error("MediaForge could not read this file.");
    const info = await response.json();
    const list = document.createElement("dl");
    list.className = "info-list";
    list.append(row("File", `${info.name} (${formatSize(info.size_bytes)})`));
    if (info.duration) list.append(row("Length", formatDuration(info.duration)));
    if (info.bitrate_kbps) list.append(row("Overall bitrate", `${info.bitrate_kbps} kbps`));
    info.video.forEach((s, i) => list.append(row(i ? "Video " + (i + 1) : "Video", describeStream(s))));
    info.audio.forEach((s, i) => list.append(row(i ? "Audio " + (i + 1) : "Audio", describeStream(s))));
    info.subtitles.forEach((s) => list.append(row("Subtitles", describeStream(s))));
    if (info.metadata) list.append(row("Hidden details", "This file carries tags such as a title, device or location."));
    t.info.replaceChildren(list);
  } catch (error) {
    t.info.hidden = true;
    setStatus(error.message, "error");
  } finally {
    t.infoBtn.disabled = !els.fileInput.files.length;
  }
}

/* Forget the info panel when another file is chosen. */
export function resetFileInfo() {
  t.info.hidden = true;
  t.info.replaceChildren();
  updateTweaks();
}

export function wireTweaks() {
  t.infoBtn.addEventListener("click", showFileInfo);
  for (const el of [t.animated, t.subsFile, els.optMute]) el.addEventListener("change", updateTweaks);
  t.coverFile.addEventListener("change", () => {
    const file = t.coverFile.files[0];
    if (t.coverPreview.src) URL.revokeObjectURL(t.coverPreview.src);
    t.coverPreview.hidden = !file;
    if (file) t.coverPreview.src = URL.createObjectURL(file);
  });
}
