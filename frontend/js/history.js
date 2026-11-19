/* History dialog. */

import { FORMAT_INFO, renderSpec, selectKind } from "./catalog.js";
import { els } from "./dom.js";
import { problemFrom, setProblem } from "./errors.js";
import { previewUrl, updateClearButton } from "./preview.js";
import { state } from "./state.js";
import { selectTab } from "./tabs.js";

function useAgain(entry) {
  els.historyDialog.close();
  selectTab("url");
  const kind = state.catalogue.audio.some((f) => f.id === entry.format) ? "audio" : "video";
  selectKind(kind, entry.format);
  if ([...els.qualitySelect.options].some((o) => o.value === entry.quality)) {
    els.qualitySelect.value = entry.quality;
    renderSpec();
  }
  els.urlInput.value = entry.url;
  updateClearButton();
  previewUrl();
}

export async function openHistory() {
  try {
    const response = await fetch("/api/history");
    if (!response.ok) throw await problemFrom(response);
    renderHistory((await response.json()).items);
    els.historyDialog.showModal();
  } catch (error) {
    setProblem(error, "History could not be opened.");
  }
}

function renderHistory(items) {
  els.historyList.replaceChildren();
  els.historyEmpty.hidden = items.length > 0;
  els.historyClear.hidden = items.length === 0;
  for (const entry of items) {
    const row = document.createElement("li");
    const name = document.createElement("span");
    name.className = "name";
    name.textContent = entry.title;
    const meta = document.createElement("small");
    const label = FORMAT_INFO[entry.format]?.label || entry.format.toUpperCase();
    meta.textContent = `${label} \u00b7 ${new Date(entry.when * 1000).toLocaleString()}`;
    name.appendChild(meta);
    const again = document.createElement("button");
    again.type = "button";
    again.className = "btn btn-quiet";
    again.textContent = "Use again";
    again.addEventListener("click", () => useAgain(entry));
    row.append(name, again);
    els.historyList.appendChild(row);
  }
}

export async function clearHistory() {
  const response = await fetch("/api/history", { method: "DELETE" });
  if (response.ok) renderHistory([]);
}
