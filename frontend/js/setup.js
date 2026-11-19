/* Setup check and tools that only work on this computer. */

import { els } from "./dom.js";
import { loadPending } from "./pending.js";

export async function checkSetup() {
  try {
    const response = await fetch("/api/health");
    const health = await response.json();
    els.quitBtn.hidden = !health.can_quit;
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
  try {
    await fetch("/api/quit", { method: "POST" });
  } catch (_) { /* the server may close the connection while stopping */ }
  const note = document.createElement("main");
  note.className = "wrap stopped";
  const title = document.createElement("h1");
  title.textContent = "MediaForge has stopped";
  const text = document.createElement("p");
  text.textContent = "You can close this tab. Double-click the MediaForge shortcut to start it again.";
  note.append(title, text);
  document.body.replaceChildren(note);
}
