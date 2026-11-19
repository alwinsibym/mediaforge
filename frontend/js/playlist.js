/* Loading a playlist and choosing videos. */

import { els } from "./dom.js";
import { problemFrom, setProblem, setStatus } from "./errors.js";
import { formatDuration } from "./format.js";
import { setBusy, submitLabel } from "./progress.js";
import { state } from "./state.js";

export function selectedEntries() {
  if (!state.playlist) return [];
  const checked = new Set(
    [...els.playlistList.querySelectorAll("input:checked")].map((box) => Number(box.value)),
  );
  return state.playlist.entries.filter((entry) => checked.has(entry.index));
}

export function updatePlaylistSelection() {
  const boxes = [...els.playlistList.querySelectorAll("input")];
  const chosen = boxes.filter((box) => box.checked).length;
  els.playlistAll.checked = chosen === boxes.length;
  els.playlistAll.indeterminate = chosen > 0 && chosen < boxes.length;
  els.playlistCount.textContent = `${chosen} of ${boxes.length} videos selected`;
  els.submitBtn.textContent = submitLabel();
  els.submitBtn.disabled = state.busy || chosen === 0;
}

export function updateFolderHint() {
  const name = state.playlist ? state.playlist.title : "playlist name";
  const dir = state.catalogue ? state.catalogue.download_dir : "downloads";
  els.folderHint.textContent = els.optFolder.checked
    ? `Files are saved in ${dir}, in a folder named after the playlist (${name}).`
    : "Nothing is kept on disk. Download the ZIP when the job finishes.";
}

function renderPlaylist(playlist) {
  els.playlistTitle.textContent = playlist.title;
  els.playlistList.replaceChildren();
  for (const entry of playlist.entries) {
    const item = document.createElement("li");
    const label = document.createElement("label");
    label.className = "check";

    const box = document.createElement("input");
    box.type = "checkbox";
    box.value = entry.index;
    box.checked = true;

    const title = document.createElement("span");
    title.className = "pl-title";
    title.textContent = `${entry.index}. ${entry.title}`;
    title.title = entry.title;

    const time = document.createElement("span");
    time.className = "pl-time";
    time.textContent = entry.duration ? formatDuration(entry.duration) : "";

    label.append(box, title, time);
    item.appendChild(label);
    els.playlistList.appendChild(item);
  }
  els.playlistBox.hidden = false;
  updatePlaylistSelection();
  updateFolderHint();
}

export async function loadPlaylist() {
  const url = els.playlistInput.value.trim();
  if (!url) {
    setStatus("Paste a playlist link first.", "error");
    els.playlistInput.focus();
    return;
  }
  setBusy(true);
  setStatus("Loading the playlist. Long playlists can take a moment...");
  try {
    const response = await fetch("/api/playlist/info", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    if (!response.ok) throw await problemFrom(response);
    state.playlist = await response.json();
    renderPlaylist(state.playlist);
    const limit = state.playlist.limit;
    setStatus(
      state.playlist.entries.length >= limit ? `Only the first ${limit} videos are listed.` : "",
    );
  } catch (error) {
    state.playlist = null;
    els.playlistBox.hidden = true;
    setProblem(error);
  } finally {
    setBusy(false);
    updatePlaylistSelection();
  }
}
