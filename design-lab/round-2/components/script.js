(() => {
  'use strict';
  const grid = document.querySelector('.button-grid');
  const status = document.getElementById('preview-status');
  const labels = {
    live: 'Live controls. Tab to a link; Enter opens the repository.',
    hover: 'Hover preview. Each link still opens the real GitHub repository.',
    focus: 'Focus preview. Tab through the links to try real keyboard focus.',
    pressed: 'Pressed preview. Links remain usable; no navigation has occurred.'
  };
  document.querySelectorAll('input[name="preview"]').forEach(input => {
    input.addEventListener('change', () => {
      if (!input.checked) return;
      grid.dataset.preview = input.value;
      status.textContent = labels[input.value];
    });
  });

  const copyButton = document.getElementById('copy-citation');
  const copyStatus = document.getElementById('copy-status');
  const citation = 'ILLUSTRATIVE EXAMPLE — not a real public record. Example review bulletin, fictional publisher, reference DEMO-001. Event: May 3. Observed: May 14. Example text: “The review event was recorded on May 3.”';
  let resetTimer;
  copyButton.addEventListener('click', async () => {
    clearTimeout(resetTimer);
    try {
      if (!navigator.clipboard?.writeText) throw new Error('Clipboard unavailable');
      await navigator.clipboard.writeText(citation);
      copyStatus.textContent = 'Example copied.';
    } catch {
      copyStatus.textContent = 'Select the example text to copy.';
    }
    resetTimer = setTimeout(() => { copyStatus.textContent = ''; }, 5000);
  });
})();
