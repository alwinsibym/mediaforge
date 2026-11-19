/* The More options section. */

import { isPreset } from "./catalog.js";
import { els } from "./dom.js";
import { state } from "./state.js";

/* Show only the extras that make sense for this tab and format. */
export function updateExtras() {
  const link = state.mode === "url";
  const video = state.kind === "video" && !isPreset();
  els.extraSponsor.hidden = state.mode === "file";
  els.extraSubs.hidden = !(video && state.mode !== "file");
  els.subsLangsField.hidden = els.extraSubs.hidden || !els.optSubs.checked;
  els.extraTrim.hidden = !link;
  els.extraChapters.hidden = !link || (state.kind === "video" && isPreset());
}

/* What the person asked for in "More options", as the server expects it. */
export function collectOptions() {
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
