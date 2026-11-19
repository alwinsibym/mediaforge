/* Link, File and Playlist tabs. */

import { renderQualityOptions, renderSpec } from "./catalog.js";
import { $, els } from "./dom.js";
import { setStatus } from "./errors.js";
import { updateExtras } from "./extras.js";
import { selectedEntries } from "./playlist.js";
import { submitLabel } from "./progress.js";
import { TABS, state } from "./state.js";

export function selectTab(mode) {
  state.mode = mode;
  for (const [name, ids] of Object.entries(TABS)) {
    const tab = $(ids.tab);
    const active = name === mode;
    tab.setAttribute("aria-selected", String(active));
    tab.tabIndex = active ? 0 : -1;
    $(ids.panel).hidden = !active;
  }
  els.submitBtn.textContent = submitLabel();
  els.submitBtn.disabled = mode === "playlist" && selectedEntries().length === 0;
  if (state.catalogue) {
    renderQualityOptions();
    renderSpec();
  }
  updateExtras();
  setStatus("");
}

export function onTabKeys(event) {
  if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
  const names = Object.keys(TABS);
  const step = event.key === "ArrowRight" ? 1 : -1;
  const next = names[(names.indexOf(state.mode) + step + names.length) % names.length];
  selectTab(next);
  $(TABS[next].tab).focus();
}
