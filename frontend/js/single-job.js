/* One link or file as a background job, and the Convert button. */

import { currentQuality, isMuted } from "./catalog.js";
import { pulseDone } from "./feedback.js";
import { buildFileForm } from "./upload-form.js";
import { els } from "./dom.js";
import { problemFrom, setProblem, setStatus } from "./errors.js";
import { collectOptions } from "./extras.js";
import { updatePlaylistSelection } from "./playlist.js";
import { pollJob, startPlaylistJob, stopPolling } from "./playlist-job.js";
import { describeProgress, setBusy, setMeter } from "./progress.js";
import { state } from "./state.js";

async function startLinkJob() {
  const url = els.urlInput.value.trim();
  if (!url) throw new Error("Paste a video link first.");
  const response = await fetch("/api/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title: (state.info && state.info.title) || "Download",
      items: [{ title: (state.info && state.info.title) || url, url }],
      format: state.format,
      quality: currentQuality() || null,
      mute: isMuted(),
      save_to_folder: false,
      make_zip: false,
      deliver_to_browser: true,
      options: { ...collectOptions(), title: els.titleInput.value.trim() },
    }),
  });
  if (!response.ok) throw await problemFrom(response);
  return response.json();
}

/* Upload with XMLHttpRequest because fetch cannot report upload progress. */
function startFileJob() {
  let data;
  try {
    data = buildFileForm();
  } catch (error) {
    return Promise.reject(error);
  }

  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    const started = Date.now();
    state.upload = request;
    request.open("POST", "/api/jobs/upload");
    request.upload.onprogress = (event) => {
      if (!event.lengthComputable) return;
      const seconds = Math.max(0.2, (Date.now() - started) / 1000);
      const speed = event.loaded / seconds;
      showProgress({
        phase: "uploading",
        percent: Math.min(99, (event.loaded / event.total) * 100),
        speed,
        eta: (event.total - event.loaded) / speed,
      });
    };
    request.onload = () => {
      state.upload = null;
      let body = {};
      try { body = JSON.parse(request.responseText); } catch (_) { /* not JSON */ }
      if (request.status >= 200 && request.status < 300) resolve(body);
      else reject(new Error(typeof body.detail === "string" ? body.detail : `The server returned an error (${request.status}).`));
    };
    request.onerror = () => {
      state.upload = null;
      reject(new Error("The upload failed. Check that MediaForge is still running."));
    };
    request.onabort = () => {
      state.upload = null;
      reject(new Error("Stopped."));
    };
    request.send(data);
  });
}

export function showProgress(item) {
  setMeter(typeof item.percent === "number" ? item.percent : null);
  els.progressText.textContent = describeProgress(item);
}

function finishSingle(kind, message, info = null) {
  stopPolling();
  state.jobId = null;
  setBusy(false);
  setStatus(message, kind, info);
  if (kind === "success") pulseDone(els.form);
}

export function renderSingleJob(job) {
  const item = job.items[0];
  if (job.status === "queued" || job.status === "running" || job.status === "uploading") {
    showProgress(item.status === "queued" ? { phase: "queued" } : item);
    return;
  }
  if (item.status === "done" && item.downloadable) {
    const link = document.createElement("a");
    link.href = `/api/jobs/${job.id}/items/${item.index}/file`;
    link.download = item.filename || "";
    document.body.appendChild(link);
    link.click();
    link.remove();
    const note = item.note ? ` ${item.note}` : "";
    finishSingle("success", `Done: ${item.filename}.${note}`);
  } else if (item.status === "failed") {
    finishSingle("error", item.error || "The conversion failed.", item.error_info);
  } else {
    finishSingle("", "Stopped.");
  }
}

async function runSingleJob() {
  setBusy(true, { showProgress: true });
  setStatus("");
  state.jobKind = "single";
  state.jobStarted = Date.now();
  try {
    const job = state.mode === "url" ? await startLinkJob() : await startFileJob();
    state.jobId = job.id;
    renderSingleJob(job);
    if (state.jobId) {
      stopPolling();
      state.poller = setInterval(pollJob, 700);
    }
  } catch (error) {
    stopPolling();
    state.jobId = null;
    setBusy(false);
    setStatus(error.message === "Stopped." ? "Stopped." : error.message || "Something went wrong.", error.message === "Stopped." ? "" : "error");
  }
}

export async function cancelSingleJob() {
  if (state.upload) {
    state.upload.abort();
    return;
  }
  if (!state.jobId) return;
  els.progressCancel.disabled = true;
  try {
    await fetch(`/api/jobs/${state.jobId}/cancel`, { method: "POST" });
    els.progressText.textContent = "Stopping...";
  } finally {
    els.progressCancel.disabled = false;
  }
}

export async function onSubmit(event) {
  event.preventDefault();
  if (state.busy || !state.catalogue) return;

  if (state.mode === "playlist") {
    setBusy(true);
    setStatus("");
    els.submitBtn.textContent = "Working through the playlist...";
    try {
      await startPlaylistJob();
    } catch (error) {
      setBusy(false);
      updatePlaylistSelection();
      setProblem(error, "Something went wrong.");
    }
    return;
  }

  await runSingleJob();
}
