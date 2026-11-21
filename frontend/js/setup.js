/* Setup check and tools that only work on this computer. */

import { els } from "./dom.js";
import { loadPending } from "./pending.js";
import { playShutdown } from "./shutdown.js";

export async function checkSetup() {
  try {
    const response = await fetch("/api/health");
    const health = await response.json();
    els.quitBtn.hidden = !health.can_quit;
    for (const label of document.querySelectorAll("[data-version]")) label.textContent = `v${health.version}`;
    if (!health.ffmpeg) {
      els.banner.textContent =
        "FFmpeg was not found on this computer, so conversions will fail. " +
        "Install it (Windows: winget install Gyan.FFmpeg), open a new terminal, " +
        "and restart MediaForge. The README has more help.";
      els.banner.hidden = false;
    }
  } catch (_) { /* loadFormats reports an unreachable server */ }
}

/* Settings and history belong to the person at the computer running MediaForge. */
export async function revealLocalTools() {
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

/* Stops the server that run.py started. Only shown on the computer running MediaForge. */
export async function quitApp() {
  if (!window.confirm("Stop MediaForge? Downloads in progress will be cancelled.")) return;
  const request = fetch("/api/quit", { method: "POST" }); // the server may close the connection while stopping
  await playShutdown(request);
}
