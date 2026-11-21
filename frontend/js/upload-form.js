/* The File tab's choices as the form the server expects (shared by Convert and the sample). */

import { currentQuality, isMuted } from "./catalog.js";
import { els } from "./dom.js";
import { state } from "./state.js";
import { collectTweaks } from "./tweaks.js";

export function buildFileForm({ forSample = false } = {}) {
  const file = els.fileInput.files[0];
  if (!file) throw new Error("Choose a file first.");
  const limitMb = state.catalogue.limits.max_upload_mb;
  if (limitMb && file.size > limitMb * 1024 * 1024) {
    throw new Error(`That file is larger than the ${limitMb} MB limit.`);
  }
  const data = new FormData();
  data.append("file", file);
  data.append("format", state.format);
  if (currentQuality()) data.append("quality", currentQuality());
  data.append("mute", String(isMuted()));
  data.append("normalize", String(els.optNormalize.checked));
  if (!forSample) data.append("title", els.fileTitleInput.value.trim());
  const tweaks = collectTweaks();
  if (tweaks.options) data.append("options", tweaks.options);
  if (tweaks.audio) data.append("audio_file", tweaks.audio);
  if (tweaks.subtitles) data.append("subtitle_file", tweaks.subtitles);
  if (tweaks.cover) data.append("cover_file", tweaks.cover);
  return data;
}
