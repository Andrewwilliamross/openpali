/* Progressive enhancement only: the page, notes, and GitHub link work without JS. */
(() => {
  const scene = document.querySelector(".field-table");
  const motion = matchMedia("(prefers-reduced-motion: reduce)");
  const fine = matchMedia("(pointer: fine)");
  let frame = 0;
  const reset = () => {
    cancelAnimationFrame(frame);
    scene.style.removeProperty("--art-x");
    scene.style.removeProperty("--art-y");
  };
  document.querySelector("main").addEventListener(
    "pointermove",
    (event) => {
      if (motion.matches || !fine.matches || innerWidth <= 900) return;
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        scene.style.setProperty(
          "--art-x",
          `${(event.clientX / innerWidth - 0.5) * 7}px`,
        );
        scene.style.setProperty(
          "--art-y",
          `${(event.clientY / innerHeight - 0.5) * 4}px`,
        );
      });
    },
    { passive: true },
  );
  document.querySelector("main").addEventListener("pointerleave", reset);
  motion.addEventListener("change", reset);
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) reset();
  });
  // Match native exclusive-details behavior on browsers that predate details[name].
  const notes = [...document.querySelectorAll('details[name="field-note"]')];
  const annotations = {
    source: ["01", "Trace it back."],
    dates: ["02", "Keep each date."],
    correction: ["03", "Leave a trail."],
  };
  notes.forEach((note) =>
    note.addEventListener("toggle", () => {
      if (note.open) {
        notes.forEach((other) => {
          if (other !== note) other.open = false;
        });
        scene.dataset.note = note.dataset.note;
        const [number, copy] = annotations[note.dataset.note];
        scene.querySelector(".annotation-index").textContent =
          `FIELD NOTE ${number}`;
        scene.querySelector(".annotation-copy").textContent = copy;
      } else if (!notes.some((item) => item.open)) delete scene.dataset.note;
    }),
  );
})();
