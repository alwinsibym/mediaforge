/* The opening screen: the logo's bars move while the page gets ready, then it fades away.
   It is shown once per browser session, and it hides itself even if the script fails
   (the CSS has a timed fallback), so it can never trap the page. */

const MINIMUM_MS = 650;
const SEEN = "mediaforge-splash";

export function splashSeen() {
  try {
    return sessionStorage.getItem(SEEN) === "1";
  } catch (_) {
    return false;
  }
}

export async function hideSplash() {
  const splash = document.getElementById("splash");
  if (!splash) return;
  const wait = Math.max(0, MINIMUM_MS - performance.now());
  await new Promise((resolve) => setTimeout(resolve, wait));
  splash.classList.add("is-leaving");
  document.documentElement.classList.add("is-ready");
  try {
    sessionStorage.setItem(SEEN, "1");
  } catch (_) { /* storage is unavailable: it will show again next time */ }
  setTimeout(() => splash.remove(), 600);
}
