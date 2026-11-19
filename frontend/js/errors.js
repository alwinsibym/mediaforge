/* Status line and the error card. */

import { els } from "./dom.js";

export function setStatus(message, kind = "", info = null) {
  els.status.className = "status" + (kind ? ` is-${kind}` : "");
  if (info) {
    els.status.replaceChildren(buildErrorCard(info, message));
    els.status.classList.add("has-card");
  } else {
    els.status.textContent = message;
  }
}

/* Shows a caught error. Errors from the server carry a full explanation in `.info`. */
export function setProblem(error, fallback = "Something went wrong.") {
  setStatus((error && error.message) || fallback, "error", error && error.info);
}

export function listBlock(heading, lines, ordered) {
  const wrap = document.createElement("div");
  wrap.className = "err-block";
  const title = document.createElement("h4");
  title.textContent = heading;
  const list = document.createElement(ordered ? "ol" : "ul");
  for (const line of lines) {
    const li = document.createElement("li");
    li.textContent = line;
    list.appendChild(li);
  }
  wrap.append(title, list);
  return wrap;
}

/* A short title and code first; the longer explanation opens on request. */
function buildErrorCard(info, message) {
  const card = document.createElement("div");
  card.className = "err-card";
  const head = document.createElement("div");
  head.className = "err-head";
  const title = document.createElement("strong");
  title.textContent = info.title;
  const code = document.createElement("code");
  code.className = "err-code";
  code.textContent = info.code;
  head.append(title, code);
  const summary = document.createElement("p");
  summary.className = "err-summary";
  summary.textContent = info.summary;
  card.append(head, summary);
  if (message && message !== info.summary && message !== info.title && message !== info.technical) {
    const detail = document.createElement("p");
    detail.className = "err-message";
    detail.textContent = message;
    card.appendChild(detail);
  }
  const more = document.createElement("details");
  more.className = "err-more";
  const toggle = document.createElement("summary");
  toggle.textContent = "What happened and what to do";
  more.appendChild(toggle);
  const what = document.createElement("p");
  what.textContent = info.what;
  more.appendChild(what);
  if (info.why && info.why.length) more.appendChild(listBlock("Why this can happen", info.why, false));
  if (info.fix && info.fix.length) more.appendChild(listBlock("What to do now", info.fix, true));
  if (info.technical) {
    const tech = document.createElement("pre");
    tech.className = "err-tech";
    tech.textContent = info.technical;
    const label = document.createElement("h4");
    label.textContent = "Technical details";
    more.append(label, tech);
  }
  card.appendChild(more);
  return card;
}

export async function problemFrom(response) {
  let message = `The server returned an error (${response.status}).`;
  let info = null;
  try {
    const body = await response.json();
    if (typeof body.detail === "string") message = body.detail;
    else if (Array.isArray(body.detail)) message = "Please check your input and try again.";
    if (body.error && body.error.code) info = body.error;
  } catch (_) { /* not JSON */ }
  const error = new Error(message);
  error.info = info;
  return error;
}
