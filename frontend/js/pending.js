/* Unfinished downloads. */

import { els } from "./dom.js";
import { problemFrom, setProblem, setStatus } from "./errors.js";
import { updatePlaylistSelection } from "./playlist.js";
import { pollJob, renderJob, stopPolling } from "./playlist-job.js";
import { setBusy } from "./progress.js";
import { state } from "./state.js";

export async function loadPending() {
  try {
    const response = await fetch("/api/pending");
    if (!response.ok) return;
    renderPending((await response.json()).items);
  } catch (_) {
    /* the list is only a convenience */
  }
}

function renderPending(items) {
  els.pendingList.replaceChildren();
  els.pending.hidden = items.length === 0;
  for (const entry of items) {
    const row = document.createElement("li");
    const name = document.createElement("span");
    name.className = "name";
    name.textContent = entry.title;
    const left = document.createElement("small");
    left.textContent = `${entry.left} video${entry.left === 1 ? "" : "s"} left`;
    name.appendChild(left);

    const resume = document.createElement("button");
    resume.type = "button";
    resume.className = "btn btn-primary";
    resume.textContent = "Resume";
    resume.addEventListener("click", () => resumePending(entry.id));
    const discard = document.createElement("button");
    discard.type = "button";
    discard.className = "btn btn-quiet";
    discard.textContent = "Remove";
    discard.addEventListener("click", async () => {
      const response = await fetch(`/api/pending/${entry.id}`, { method: "DELETE" });
      if (response.ok) renderPending((await response.json()).items);
    });
    const actions = document.createElement("span");
    actions.className = "actions";
    actions.append(resume, discard);
    row.append(name, actions);
    els.pendingList.appendChild(row);
  }
}

async function resumePending(id) {
  if (state.busy) {
    setStatus("Wait for the current download to finish, then resume.", "error");
    return;
  }
  setBusy(true);
  setStatus("");
  els.submitBtn.textContent = "Working through the playlist...";
  try {
    const response = await fetch(`/api/pending/${id}/resume`, { method: "POST" });
    if (!response.ok) throw await problemFrom(response);
    const { request, ...job } = await response.json();
    state.lastBody = request;
    state.jobId = job.id;
    state.jobKind = "playlist";
    state.jobStarted = Date.now();
    els.pending.hidden = true;
    renderJob(job);
    stopPolling();
    state.poller = setInterval(pollJob, 1000);
  } catch (error) {
    setBusy(false);
    updatePlaylistSelection();
    setProblem(error, "Something went wrong.");
  }
}
