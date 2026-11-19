/* System, Light or Dark theme. */

import { els } from "./dom.js";

const THEME_KEY = "mediaforge-theme";

export function savedTheme() {
  try {
    const value = localStorage.getItem(THEME_KEY);
    return value === "light" || value === "dark" ? value : "system";
  } catch (_) {
    return "system";
  }
}

export function applyTheme(choice) {
  const root = document.documentElement;
  if (choice === "system") root.removeAttribute("data-theme");
  else root.dataset.theme = choice;
  for (const button of els.themeSwitch.querySelectorAll("button")) {
    button.setAttribute("aria-checked", String(button.dataset.themeChoice === choice));
  }
}

export function chooseTheme(choice) {
  applyTheme(choice);
  try {
    if (choice === "system") localStorage.removeItem(THEME_KEY);
    else localStorage.setItem(THEME_KEY, choice);
  } catch (_) { /* the choice just will not be remembered */ }
}
