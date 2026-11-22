/* Setup check and tools that only work on this computer. */

import { els } from "./dom.js";
import { loadPending } from "./pending.js";
import { playShutdown } from "./shutdown.js";

function showFfmpegBanner(canInstall) {
  els.banner.replaceChildren();
  els.banner.append(
    "FFmpeg was not found on this computer, so conversions will fail. " +
      (canInstall
        ? "MediaForge can install it for you (a download of about 100 MB)."
        : "Install it (Windows: winget install Gyan.FFmpeg), open a new terminal, " +
          "and restart MediaForge. The README has more help."),
  );
  if (canInstall) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "btn btn-quiet banner-btn";
    button.textContent = "Install FFmpeg";
    button.addEventListener("click", () => installFfmpeg(button));
    els.banner.append(" ", button);
  }
  els.banner.hidden = false;
}

async function installFfmpeg(button) {
  button.disabled = true;
  button.textContent = "Installing... this can take a few minutes";
  try {
    const response = await fetch("/api/install-ffmpeg", { method: "POST" });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail || "The installation failed.");
    els.banner.hidden = true;
  } catch (error) {
    button.disabled = false;
    button.textContent = "Try again";
    els.banner.append(` ${error.message}`);
  }
}

export async function checkSetup() {
  try {
    const response = await fetch("/api/health");
    const health = await response.json();
    els.quitBtn.hidden = !health.can_quit;
    for (const label of document.querySelectorAll("[data-version]")) label.textContent = `v${health.version}`;
    if (!health.ffmpeg) showFfmpegBanner(health.can_install_ffmpeg);
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
