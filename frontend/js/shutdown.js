/* The goodbye when MediaForge is switched off: the page dims, the logo's bars settle,
   then the screen closes like a display being turned off. */

const STEPS = { settle: 1100, close: 900 };

function pause(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function buildOverlay() {
  const overlay = document.createElement("div");
  overlay.className = "shutdown";
  overlay.setAttribute("role", "status");
  const mark = document.querySelector(".brand .mark");
  const logo = mark ? mark.cloneNode(true) : document.createElement("div");
  logo.classList.add("shutdown-logo");
  const title = document.createElement("p");
  title.className = "shutdown-title";
  title.textContent = "Shutting down...";
  const text = document.createElement("p");
  text.className = "shutdown-text";
  overlay.append(logo, title, text);
  return { overlay, title, text };
}

/* Plays the goodbye while `stopRequest` (a promise) finishes. Resolves when the screen is dark. */
export async function playShutdown(stopRequest) {
  const { overlay, title, text } = buildOverlay();
  document.body.append(overlay);
  document.body.classList.add("is-stopping");
  await Promise.all([stopRequest.catch(() => {}), pause(STEPS.settle)]);

  overlay.classList.add("is-stopped");
  title.textContent = "MediaForge has stopped";
  text.textContent = "You can close this tab. Double-click the MediaForge shortcut to start it again.";
  await pause(STEPS.close);
  document.body.classList.add("is-off");
}
