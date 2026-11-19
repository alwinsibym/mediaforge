/* Busy state, progress bar and the waveform. */

import { els } from "./dom.js";
import { formatClock, formatSpeed, formatTimeLeft } from "./format.js";
import { selectedEntries } from "./playlist.js";
import { state } from "./state.js";

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
export function describeProgress(item) {
  const label = PHASE_TEXT[item.phase] || "Working";
  const percent = typeof item.percent === "number" ? ` ${Math.floor(item.percent)}%` : "";
  return [label + percent, formatSpeed(item.speed), formatTimeLeft(item.eta)]
    .filter(Boolean)
    .join(" \u00b7 ");
}

export function setMeter(percent) {
  const known = typeof percent === "number";
  els.meter.classList.toggle("is-indeterminate", !known);
  els.meterFill.style.width = known ? `${percent}%` : "";
  els.meterPercent.textContent = known ? `${Math.floor(percent)}%` : "";
  if (known) els.meter.setAttribute("aria-valuenow", String(Math.floor(percent)));
  else els.meter.removeAttribute("aria-valuenow");
}

export function buildWave() {
  const heights = [30, 55, 80, 45, 95, 60, 35, 75, 100, 50, 70, 40, 90, 65, 30, 85, 55, 100, 45, 75, 35, 60, 90, 50];
  heights.forEach((height, index) => {
    const bar = document.createElement("span");
    bar.style.setProperty("--h", height);
    bar.style.setProperty("--i", index);
    els.wave.appendChild(bar);
  });
}

export function submitLabel() {
  if (state.mode !== "playlist") return "Convert and download";
  const count = selectedEntries().length;
  if (!state.playlist) return "Load a playlist first";
  return count === 1 ? "Convert 1 video" : `Convert ${count} videos`;
}

export function setBusy(busy, { showProgress = false } = {}) {
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
