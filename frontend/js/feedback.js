/* Small confirmations: an animated tick for finished work, and a soft pulse on the card. */

const SVG = "http://www.w3.org/2000/svg";

function svg(name, attributes) {
  const element = document.createElementNS(SVG, name);
  for (const [key, value] of Object.entries(attributes)) element.setAttribute(key, value);
  return element;
}

/* A circle that draws itself, then a tick. Decorative, so it is hidden from screen readers. */
export function tickElement() {
  const wrapper = document.createElement("span");
  wrapper.className = "tick";
  const picture = svg("svg", { viewBox: "0 0 24 24", "aria-hidden": "true", focusable: "false" });
  picture.append(
    svg("circle", { class: "tick-ring", cx: "12", cy: "12", r: "10", pathLength: "1" }),
    svg("path", { class: "tick-path", d: "M7.2 12.6l3.2 3.2 6.4-6.8", pathLength: "1" }),
  );
  wrapper.append(picture);
  return wrapper;
}

/* One gentle pulse around a card when something finishes. */
export function pulseDone(element) {
  if (!element) return;
  element.classList.remove("is-done");
  void element.offsetWidth; // restart the animation if it was already running
  element.classList.add("is-done");
  setTimeout(() => element.classList.remove("is-done"), 1600);
}
