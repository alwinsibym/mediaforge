/* Link preview, thumbnail download. */

import { renderQualityOptions, renderSpec } from "./catalog.js";
import { els } from "./dom.js";
import { problemFrom, setProblem, setStatus } from "./errors.js";
import { filenameFrom, formatCount, formatDuration, formatSize, formatUploadDate, looksLikeUrl, saveBlob } from "./format.js";
import { setBusy } from "./progress.js";
import { state } from "./state.js";

export function updateClearButton() {
  els.clearBtn.hidden = !els.urlInput.value;
}

function resetPreview() {
  clearTimeout(state.previewTimer);
  state.info = null;
  state.previewedUrl = "";
  els.titleInput.value = "";
  els.preview.hidden = true;
  els.thumbTools.hidden = true;
  if (state.catalogue) {
    renderQualityOptions();
    renderSpec();
  }
}

export function clearUrl() {
  els.urlInput.value = "";
  resetPreview();
  updateClearButton();
  els.urlInput.focus();
}

function showPreview(info) {
  state.info = info;
  els.previewTitle.textContent = info.title;
  els.titleInput.value = "";
  els.titleInput.placeholder = info.title;
  els.previewMeta.textContent = [
    info.uploader,
    formatDuration(info.duration),
    info.view_count ? `${formatCount(info.view_count)} views` : "",
    formatUploadDate(info.upload_date),
  ]
    .filter(Boolean)
    .join(" · ");

  const top = info.qualities[0];
  els.previewQuality.textContent = top
    ? `Available up to ${top.label}${info.qualities.length > 1 ? `, ${info.qualities.length} video qualities` : ""}`
    : "No video qualities listed. Audio formats still work.";

  if (info.thumbnail) {
    els.previewThumb.src = info.thumbnail;
    els.previewThumb.hidden = false;
  } else {
    els.previewThumb.hidden = true;
  }

  els.thumbSize.replaceChildren();
  for (const size of info.thumbnails) {
    const option = document.createElement("option");
    option.value = size.id;
    option.textContent = size.label;
    els.thumbSize.appendChild(option);
  }
  els.thumbTools.hidden = info.thumbnails.length === 0;
  els.preview.hidden = false;
  renderQualityOptions();
  renderSpec();
}

export async function previewUrl({ quiet = false } = {}) {
  const url = els.urlInput.value.trim();
  if (!url) {
    if (!quiet) setStatus("Paste a video link first.", "error");
    els.urlInput.focus();
    return;
  }
  if (url === state.previewedUrl && state.info) return;
  setBusy(true);
  setStatus("Looking up the video...");
  try {
    const response = await fetch("/api/info", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    if (!response.ok) throw await problemFrom(response);
    const info = await response.json();
    if (els.urlInput.value.trim() !== url) return; // the link changed while we waited
    state.previewedUrl = url;
    showPreview(info);
    setStatus("");
  } catch (error) {
    if (els.urlInput.value.trim() === url) {
      resetPreview();
      setProblem(error);
    }
  } finally {
    setBusy(false);
  }
}

/* Look up the link by itself once it has been pasted or typed. */
export function onUrlInput() {
  updateClearButton();
  clearTimeout(state.previewTimer);
  const url = els.urlInput.value.trim();
  if (url !== state.previewedUrl) {
    state.info = null;
    els.preview.hidden = true;
    // A new link means the last result (done or failed) is no longer the story.
    if (!state.busy) setStatus("");
    if (state.catalogue) {
      renderQualityOptions();
      renderSpec();
    }
  }
  if (looksLikeUrl(url) && !state.busy) {
    state.previewTimer = setTimeout(() => previewUrl({ quiet: true }), 700);
  }
}

export async function downloadThumbnail() {
  const url = state.previewedUrl;
  if (!url || !els.thumbSize.value) return;
  els.thumbDownload.disabled = true;
  try {
    const response = await fetch("/api/thumbnail", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url,
        id: els.thumbSize.value,
        format: els.thumbFormat.value,
        square: els.thumbSquare.checked,
      }),
    });
    if (!response.ok) throw await problemFrom(response);
    const blob = await response.blob();
    const name = filenameFrom(response, `thumbnail.${els.thumbFormat.value}`);
    saveBlob(blob, name);
    setStatus(`Saved ${name} (${formatSize(blob.size)})`, "success");
  } catch (error) {
    setProblem(error, "The thumbnail could not be saved.");
  } finally {
    els.thumbDownload.disabled = false;
  }
}
