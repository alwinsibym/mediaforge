/* Running a playlist as a background job. */

import { currentQuality, isMuted } from "./catalog.js";
import { els } from "./dom.js";
import { listBlock, problemFrom, setProblem, setStatus } from "./errors.js";
import { collectOptions } from "./extras.js";
import { formatSpeed, formatTimeLeft } from "./format.js";
import { loadPending } from "./pending.js";
import { selectedEntries, updatePlaylistSelection } from "./playlist.js";
import { describeProgress, setBusy } from "./progress.js";
import { renderSingleJob } from "./single-job.js";
import { state } from "./state.js";

const STATE_TEXT = {
  queued: "Waiting",
  running: "Converting",
  done: "Done",
  failed: "Failed",
  skipped: "Skipped",
};

export function renderJob(job) {
  const finished = job.status === "done" || job.status === "cancelled";
  const handled = job.items.filter((item) => ["done", "failed", "skipped"].includes(item.status));
  els.job.hidden = false;
  const active = job.items.filter((item) => item.status === "running");
  const fraction = active.reduce(
    (sum, item) => sum + (typeof item.percent === "number" ? item.percent / 100 : 0),
    0,
  );
  const overall = finished ? 1 : Math.min(1, (handled.length + fraction) / job.total);
  els.jobBar.style.width = `${overall * 100}%`;

  if (finished || active.length === 0) {
    els.jobDetail.textContent = "";
  } else {
    const parts = [];
    if (active.length === 1) {
      parts.push(describeProgress(active[0]));
    } else {
      const speed = active.reduce((sum, item) => sum + (item.speed || 0), 0);
      parts.push(`${active.length} at a time`, formatSpeed(speed));
    }
    const elapsed = (Date.now() - state.jobStarted) / 1000;
    if (handled.length >= 1 && overall > 0) {
      parts.push(formatTimeLeft((elapsed / overall) * (1 - overall)).replace(" left", " left overall"));
    }
    els.jobDetail.textContent = parts.filter(Boolean).join(" \u00b7 ");
  }

  state.failedItems = finished
    ? job.items
        .filter((item) => ["failed", "skipped"].includes(item.status) && item.url)
        .map((item) => ({ title: item.title, url: item.url, number: item.number }))
    : [];
  els.jobRetry.hidden = state.failedItems.length === 0;
  els.jobRetry.textContent = `Retry ${state.failedItems.length}`;
  els.jobNotice.hidden = !(finished && job.blocked);
  if (job.blocked) {
    els.jobNotice.textContent =
      job.blocked_reason === "network"
        ? "MediaForge could not reach the site, so it stopped instead of failing every video. " +
          "Check your internet connection, then choose Retry. The videos already saved are kept."
        : "The site kept asking for a sign-in check, so MediaForge stopped before it got worse. " +
          "Open Settings and choose the browser where you are signed in, wait a few minutes, " +
          "then choose Retry. The videos already saved are kept.";
  }

  const failed = job.failed ? `, ${job.failed} failed` : "";
  els.jobSummary.textContent = finished
    ? `${job.status === "cancelled" ? "Stopped" : "Finished"}: ${job.done} of ${job.total} converted${failed}`
    : `Converting ${handled.length + 1 > job.total ? job.total : handled.length + 1} of ${job.total}${failed}`;
  els.jobCancel.hidden = finished;

  els.jobItems.replaceChildren();
  for (const item of job.items) {
    const row = document.createElement("li");
    row.className = `is-${item.status}`;
    const stateLabel = document.createElement("span");
    stateLabel.className = "state";
    if (item.status === "running" && item.phase === "waiting") stateLabel.textContent = "Paused";
    else if (item.status === "running" && typeof item.percent === "number") {
      stateLabel.textContent = `${Math.floor(item.percent)}%`;
    } else stateLabel.textContent = STATE_TEXT[item.status] || item.status;
    const name = document.createElement("span");
    name.className = "name";
    name.textContent = item.filename || item.title;
    for (const text of [item.error, item.note]) {
      if (!text) continue;
      const reason = document.createElement("small");
      reason.textContent = text;
      name.appendChild(reason);
    }
    if (item.error_info) {
      const info = item.error_info;
      const more = document.createElement("details");
      more.className = "err-row";
      const toggle = document.createElement("summary");
      toggle.textContent = `${info.title} (${info.code})`;
      more.appendChild(toggle);
      const what = document.createElement("p");
      what.textContent = info.what;
      more.appendChild(what);
      if (info.fix && info.fix.length) more.appendChild(listBlock("What to do now", info.fix, true));
      name.appendChild(more);
    }
    row.append(stateLabel, name);
    els.jobItems.appendChild(row);
  }

  els.jobActions.hidden = !(finished && (job.folder || job.zip_ready));
  els.jobOpen.hidden = !job.folder || !isThisComputer();
  els.jobZip.hidden = !job.zip_ready;
  if (job.zip_ready) els.jobZip.href = `/api/jobs/${job.id}/zip`;
}

/* The folder lives on the computer running MediaForge, which may not be this device. */
function isThisComputer() {
  return ["localhost", "127.0.0.1", "[::1]", "::1"].includes(location.hostname);
}

export function stopPolling() {
  clearInterval(state.poller);
  state.poller = null;
}

export async function pollJob() {
  try {
    const response = await fetch(`/api/jobs/${state.jobId}`);
    if (!response.ok) throw await problemFrom(response);
    const job = await response.json();
    if (state.jobKind === "single") {
      renderSingleJob(job);
      return;
    }
    renderJob(job);
    if (job.status === "done" || job.status === "cancelled") {
      stopPolling();
      setBusy(false);
      updatePlaylistSelection();
      loadPending();
      if (job.folder) {
        const where = isThisComputer() ? "" : " (on the computer running MediaForge)";
        setStatus(`Saved to ${job.folder}${where}`, "success");
      }
      else if (job.zip_ready) setStatus("Your ZIP is ready. Use Download ZIP.", "success");
      else setStatus("No videos could be converted.", "error");
    }
  } catch (error) {
    stopPolling();
    setBusy(false);
    setProblem(error, "Lost contact with the server.");
  }
}

export async function startPlaylistJob({ retry = false } = {}) {
  let body;
  if (retry) {
    if (!state.lastBody || state.failedItems.length === 0) throw new Error("Nothing to retry.");
    body = { ...state.lastBody, items: state.failedItems, continue_job: state.jobId };
  } else {
    const entries = selectedEntries();
    if (!state.playlist || entries.length === 0) throw new Error("Select at least one video.");
    if (!els.optFolder.checked && !els.optZip.checked) {
      throw new Error("Choose a folder, a ZIP, or both.");
    }
    body = {
      title: state.playlist.title,
      items: entries.map(({ title, url }) => ({ title, url })),
      format: state.format,
      quality: currentQuality() || null,
      mute: isMuted(),
      save_to_folder: els.optFolder.checked,
      make_zip: els.optZip.checked,
      options: collectOptions(),
    };
  }
  const response = await fetch("/api/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw await problemFrom(response);
  const job = await response.json();
  state.lastBody = { ...body, continue_job: undefined };
  state.jobId = job.id;
  state.jobKind = "playlist";
  state.jobStarted = Date.now();
  renderJob(job);
  stopPolling();
  state.poller = setInterval(pollJob, 1000);
}

export async function retryFailed() {
  if (state.busy) return;
  setBusy(true);
  setStatus("");
  els.submitBtn.textContent = "Working through the playlist...";
  try {
    await startPlaylistJob({ retry: true });
  } catch (error) {
    setBusy(false);
    updatePlaylistSelection();
    setProblem(error, "Something went wrong.");
  }
}

export async function cancelJob() {
  if (!state.jobId) return;
  els.jobCancel.disabled = true;
  try {
    await fetch(`/api/jobs/${state.jobId}/cancel`, { method: "POST" });
    setStatus("Stopping after the current video...");
  } finally {
    els.jobCancel.disabled = false;
  }
}

export async function openJobFolder() {
  try {
    const response = await fetch(`/api/jobs/${state.jobId}/open-folder`, { method: "POST" });
    if (!response.ok) throw await problemFrom(response);
  } catch (error) {
    setProblem(error);
  }
}

/* ---------- convert ---------- */
