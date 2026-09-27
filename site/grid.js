// Decorative only: the complete page and its GitHub link work without JavaScript.
const grid = document.querySelector('.contribution-grid');
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
const finePointer = window.matchMedia('(pointer: fine)');
let nearby = [];
function clearHighlight() {
  nearby.forEach((cell) => cell.classList.remove('is-near'));
  nearby = [];
  grid?.classList.remove('is-awake');
}
if (grid) {
  grid.addEventListener('pointermove', (event) => {
    if (reducedMotion.matches || !finePointer.matches) return;
    const cell = event.target.closest('.cell');
    if (!cell || !grid.contains(cell)) return;
    clearHighlight();
    const index = Number(cell.dataset.index);
    const row = Math.floor(index / 25);
    const column = index % 25;
    nearby = [...grid.children].filter((candidate) => {
      const other = Number(candidate.dataset.index);
      return Math.abs(Math.floor(other / 25) - row) <= 1 && Math.abs(other % 25 - column) <= 1;
    });
    grid.classList.add('is-awake');
    nearby.forEach((candidate) => candidate.classList.add('is-near'));
  });
  grid.addEventListener('pointerleave', clearHighlight);
  reducedMotion.addEventListener('change', clearHighlight);
  finePointer.addEventListener('change', clearHighlight);
}
