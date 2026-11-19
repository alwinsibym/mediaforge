/* Access token login. */

import { $ } from "./dom.js";
import { problemFrom } from "./errors.js";

/* When the computer running MediaForge set an access token, other devices enter it once. */
export async function ensureLoggedIn() {
  try {
    const response = await fetch("/api/health");
    const health = await response.json();
    if (!health.auth_required || health.authorised) return;
  } catch (_) {
    return;
  }
  const dialog = $("login-dialog");
  dialog.addEventListener("cancel", (event) => event.preventDefault());
  await new Promise((resolve) => {
    $("login-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const status = $("login-status");
      status.className = "status";
      status.textContent = "";
      try {
        const response = await fetch("/api/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token: $("login-token").value }),
        });
        if (!response.ok) throw await problemFrom(response);
        dialog.close();
        resolve();
      } catch (error) {
        status.className = "status is-error";
        status.textContent = error.message || "That token did not work.";
      }
    });
    dialog.showModal();
  });
}
