/* Settings dialog (this computer only). */

import { els } from "./dom.js";
import { problemFrom, setProblem, setStatus } from "./errors.js";

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

export async function openSettings() {
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
    els.setProxy.value = saved.proxy || "";
    els.setImpersonate.checked = saved.impersonate && saved.impersonation_installed;
    els.setImpersonate.disabled = !saved.impersonation_installed;
    els.impersonateHint.textContent = saved.impersonation_installed
      ? "Can help with sites that refuse downloaders (some Reddit and Cloudflare-protected pages)."
      : "Needs the curl_cffi package: run  pip install curl_cffi  then restart MediaForge.";
    els.ytdlpVersion.textContent = health.yt_dlp ? `Installed: yt-dlp ${health.yt_dlp}.` : "";
    els.settingsDialog.showModal();
  } catch (error) {
    setProblem(error, "Settings could not be opened.");
  }
}

export async function saveSettings(event) {
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
        proxy: els.setProxy.value.trim(),
        impersonate: els.setImpersonate.checked,
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

export async function updateYtdlp() {
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

export function closeOnBackdrop(dialog) {
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });
}
