/* Starts the page: connects buttons to their actions. */

import { ensureLoggedIn } from "./auth.js";
import { loadFormats, renderQualityOptions, renderSpec, selectKind } from "./catalog.js";
import { els } from "./dom.js";
import { updateExtras } from "./extras.js";
import { wireTweaks } from "./tweaks.js";
import { setupDropzone } from "./files.js";
import { clearHistory, openHistory } from "./history.js";
import { loadPlaylist, updateFolderHint, updatePlaylistSelection } from "./playlist.js";
import { cancelJob, openJobFolder, retryFailed } from "./playlist-job.js";
import { clearUrl, downloadThumbnail, onUrlInput, previewUrl } from "./preview.js";
import { buildWave } from "./progress.js";
import { closeOnBackdrop, openSettings, saveSettings, updateYtdlp } from "./settings.js";
import { checkSetup, quitApp, revealLocalTools } from "./setup.js";
import { cancelSingleJob, onSubmit } from "./single-job.js";
import { state } from "./state.js";
import { onTabKeys, selectTab } from "./tabs.js";
import { applyTheme, chooseTheme, savedTheme } from "./theme.js";

async function startUp() {
  await ensureLoggedIn();
  loadFormats();
  checkSetup();
  revealLocalTools();
}

els.tabUrl.addEventListener("click", () => selectTab("url"));
els.tabFile.addEventListener("click", () => selectTab("file"));
els.tabPlaylist.addEventListener("click", () => selectTab("playlist"));
for (const tab of [els.tabUrl, els.tabFile, els.tabPlaylist]) tab.addEventListener("keydown", onTabKeys);

els.playlistLoad.addEventListener("click", loadPlaylist);
els.playlistInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    loadPlaylist();
  }
});
els.playlistAll.addEventListener("change", () => {
  for (const box of els.playlistList.querySelectorAll("input")) box.checked = els.playlistAll.checked;
  updatePlaylistSelection();
});
els.playlistList.addEventListener("change", updatePlaylistSelection);
els.optFolder.addEventListener("change", updateFolderHint);
els.jobCancel.addEventListener("click", cancelJob);
els.jobRetry.addEventListener("click", retryFailed);
els.settingsBtn.addEventListener("click", openSettings);
els.historyBtn.addEventListener("click", openHistory);
els.quitBtn.addEventListener("click", quitApp);
els.settingsForm.addEventListener("submit", saveSettings);
els.settingsClose.addEventListener("click", () => els.settingsDialog.close());
els.ytdlpUpdate.addEventListener("click", updateYtdlp);
els.historyClose.addEventListener("click", () => els.historyDialog.close());
els.historyClear.addEventListener("click", clearHistory);
closeOnBackdrop(els.settingsDialog);
closeOnBackdrop(els.historyDialog);
els.progressCancel.addEventListener("click", cancelSingleJob);
applyTheme(savedTheme());
els.themeSwitch.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-theme-choice]");
  if (button) chooseTheme(button.dataset.themeChoice);
});
els.jobOpen.addEventListener("click", openJobFolder);

for (const input of els.kindInputs) {
  input.addEventListener("change", () => input.checked && state.catalogue && selectKind(input.value));
}
els.chips.addEventListener("change", (event) => {
  if (event.target.name !== "format") return;
  state.format = event.target.value;
  renderQualityOptions();
  renderSpec();
  updateExtras();
});
els.qualitySelect.addEventListener("change", renderSpec);
els.optSubs.addEventListener("change", updateExtras);
wireTweaks();

els.urlInput.addEventListener("input", onUrlInput);
els.urlInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    clearTimeout(state.previewTimer);
    previewUrl();
  }
});
els.thumbDownload.addEventListener("click", downloadThumbnail);
els.optMute.addEventListener("change", renderSpec);
els.clearBtn.addEventListener("click", clearUrl);
els.previewBtn.addEventListener("click", () => previewUrl());
els.form.addEventListener("submit", onSubmit);

buildWave();
setupDropzone();

startUp();
