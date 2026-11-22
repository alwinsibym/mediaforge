/* Theme switch, frosted header on scroll, and a Download button that finds the newest release. */
(function () {
  "use strict";
  var KEY = "mediaforge-site-theme";
  var root = document.documentElement;

  function paint(choice) {
    if (choice === "system") root.removeAttribute("data-theme");
    else root.dataset.theme = choice;
    document.querySelectorAll("#theme button").forEach(function (b) {
      b.setAttribute("aria-checked", String(b.dataset.choice === choice));
    });
  }
  var current = root.dataset.theme || "system";
  paint(current);
  document.getElementById("theme").addEventListener("click", function (event) {
    var button = event.target.closest("button");
    if (!button) return;
    paint(button.dataset.choice);
    try {
      if (button.dataset.choice === "system") localStorage.removeItem(KEY);
      else localStorage.setItem(KEY, button.dataset.choice);
    } catch (e) { /* the choice just will not be remembered */ }
  });

  var bar = document.getElementById("bar");
  function onScroll() { bar.classList.toggle("is-scrolled", window.scrollY > 8); }
  onScroll();
  window.addEventListener("scroll", onScroll, { passive: true });

  /* Point Download at the newest Windows zip. If GitHub cannot be reached, the buttons
     keep their link to the Releases page, which always works. */
  fetch("https://api.github.com/repos/alwinsibym/mediaforge/releases/latest", { headers: { Accept: "application/vnd.github+json" } })
    .then(function (r) { return r.ok ? r.json() : Promise.reject(); })
    .then(function (release) {
      var zip = (release.assets || []).find(function (a) { return /windows\.zip$/i.test(a.name); });
      var version = String(release.tag_name || "").replace(/^v/, "");
      var meta = document.getElementById("download-meta");
      if (version && meta) {
        var size = zip ? " · " + Math.round(zip.size / 1048576) + " MB" : "";
        meta.textContent = "v" + version + size;
      }
      if (zip) {
        ["download", "download-2"].forEach(function (id) {
          var link = document.getElementById(id);
          if (link) link.href = zip.browser_download_url;
        });
      }
    })
    .catch(function () { /* keep the fallback link */ });
})();
