(() => {
  'use strict';
  const sculpture = document.getElementById('sculpture-wrap');
  const page = document.getElementById('page');
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const finePointer = window.matchMedia('(pointer: fine)');
  let frame;

  function reset() {
    sculpture.style.setProperty('--move-x', '0px');
    sculpture.style.setProperty('--move-y', '0px');
  }

  page.addEventListener('pointermove', (event) => {
    if (reducedMotion.matches || !finePointer.matches) return;
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(() => {
      const bounds = page.getBoundingClientRect();
      const x = ((event.clientX - bounds.left) / bounds.width - 0.5) * 14;
      const y = ((event.clientY - bounds.top) / bounds.height - 0.5) * 10;
      sculpture.style.setProperty('--move-x', `${x.toFixed(2)}px`);
      sculpture.style.setProperty('--move-y', `${y.toFixed(2)}px`);
    });
  }, { passive: true });

  page.addEventListener('pointerleave', reset);
  reducedMotion.addEventListener('change', reset);
})();
