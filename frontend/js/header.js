// The header is see-through at the top of the page and turns to frosted glass once you scroll.
const header = document.querySelector(".site-header");

function update() {
  header?.classList.toggle("is-scrolled", window.scrollY > 8);
}

export function wireHeader() {
  if (!header) return;
  update();
  window.addEventListener("scroll", update, { passive: true });
}
