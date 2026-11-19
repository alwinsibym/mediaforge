/* Setup check and tools that only work on this computer. */

import { els } from "./dom.js";
import { loadPending } from "./pending.js";

export async function checkSetup() {
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
