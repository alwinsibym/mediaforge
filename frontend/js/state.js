/* The values the page keeps while it runs. */

export const state = {
  mode: "url",
  kind: "audio",
  format: "mp3",
  catalogue: null,
  busy: false,
  timer: null,
  playlist: null,
  jobId: null,
  poller: null,
  info: null,
  previewedUrl: "",
  previewTimer: null,
  jobKind: "single",
  jobStarted: 0,
  upload: null,
  failedItems: [],
  lastBody: null,
};

export const TABS = {
  url: { tab: "tab-url", panel: "panel-url" },
  file: { tab: "tab-file", panel: "panel-file" },
  playlist: { tab: "tab-playlist", panel: "panel-playlist" },
};
