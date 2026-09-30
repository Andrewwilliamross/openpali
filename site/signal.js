(() => {
  "use strict";
  const field = document.querySelector(".signal-field svg");
  if (!field) return;
  const reduced = matchMedia("(prefers-reduced-motion: reduce)");
  const finePointer = matchMedia("(hover: hover) and (pointer: fine)");
  const tiles = [...field.querySelectorAll("rect")]
    .filter((tile) => Number(tile.getAttribute("width")) < 40)
    .map((node) => {
      const size = Number(node.getAttribute("width"));
      return {
        node,
        size,
        x: Number(node.getAttribute("x")) + size / 2,
        y: Number(node.getAttribute("y")) + size / 2,
        opacity: Number(
          node.getAttribute("opacity") ||
            node.getAttribute("fill-opacity") ||
            1,
        ),
        active: false,
      };
    });
  let point = { x: -1000, y: -1000 };
  let current = { ...point };
  let strength = 0;
  let targetStrength = 0;
  let frame = null;
  let visible = true;
  const enabled = () =>
    !reduced.matches && finePointer.matches && visible && !document.hidden;
  function restoreTile(tile) {
    tile.node.setAttribute("x", tile.x - tile.size / 2);
    tile.node.setAttribute("y", tile.y - tile.size / 2);
    tile.node.setAttribute("width", tile.size);
    tile.node.setAttribute("height", tile.size);
    tile.node.setAttribute("opacity", tile.opacity);
    tile.active = false;
  }
  function restore() {
    for (const tile of tiles) if (tile.active) restoreTile(tile);
  }
  function requestFrame() {
    if (frame === null && enabled()) frame = requestAnimationFrame(render);
  }
  function render() {
    frame = null;
    if (!enabled()) return;
    current.x += (point.x - current.x) * 0.18;
    current.y += (point.y - current.y) * 0.18;
    strength += (targetStrength - strength) * 0.13;
    if (Math.abs(strength - targetStrength) < 0.001) strength = targetStrength;
    for (const tile of tiles) {
      const distance = Math.hypot(tile.x - current.x, tile.y - current.y);
      const influence = Math.max(0, 1 - distance / 150) ** 2 * strength;
      if (influence < 0.001) {
        if (tile.active) restoreTile(tile);
        continue;
      }
      const size = tile.size + influence * 7;
      tile.node.setAttribute("x", (tile.x - size / 2).toFixed(3));
      tile.node.setAttribute("y", (tile.y - size / 2).toFixed(3));
      tile.node.setAttribute("width", size.toFixed(3));
      tile.node.setAttribute("height", size.toFixed(3));
      tile.node.setAttribute(
        "opacity",
        Math.min(1, tile.opacity + influence * 0.42).toFixed(3),
      );
      tile.active = influence >= 0.001;
    }
    if (
      Math.abs(strength - targetStrength) > 0.001 ||
      (targetStrength > 0 &&
        Math.hypot(point.x - current.x, point.y - current.y) > 0.15)
    )
      requestFrame();
    else if (!targetStrength) restore();
  }
  document.querySelector(".page").addEventListener(
    "pointermove",
    (event) => {
      if (!enabled() || event.pointerType === "touch") return;
      if (
        event.target instanceof Element &&
        event.target.closest(".hero, .header, .footer")
      ) {
        targetStrength = 0;
        requestFrame();
        return;
      }
      const matrix = field.getScreenCTM();
      if (!matrix) return;
      const local = new DOMPoint(event.clientX, event.clientY).matrixTransform(
        matrix.inverse(),
      );
      if (!targetStrength) current = { x: local.x, y: local.y };
      point = { x: local.x, y: local.y };
      targetStrength = 1;
      requestFrame();
    },
    { passive: true },
  );
  document.querySelector(".page").addEventListener("pointerleave", () => {
    targetStrength = 0;
    requestFrame();
  });
  function suspend() {
    if (frame !== null) cancelAnimationFrame(frame);
    frame = null;
    targetStrength = 0;
    strength = 0;
    restore();
  }
  reduced.addEventListener("change", suspend);
  finePointer.addEventListener("change", suspend);
  document.addEventListener("visibilitychange", suspend);
  window.addEventListener("pagehide", suspend);
  if ("IntersectionObserver" in window)
    new IntersectionObserver((entries) => {
      visible = entries[0].isIntersecting;
      if (!visible) suspend();
    }).observe(field);
})();
