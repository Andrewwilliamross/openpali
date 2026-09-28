(() => {
  'use strict';
  const reader = document.querySelector('.reader');
  const control = document.getElementById('date-stage');
  const buttons = [...document.querySelectorAll('.stage-buttons button')];
  const windows = ['event', 'observed', 'published'].map(name => document.getElementById(`date-${name}`));
  const states = [
    { mode: 'EVENT OCCURRED', caption: 'An event can happen before its public record is available to us.', spoken: 'Event occurred. May 3. Not yet observed or published.' },
    { mode: 'RECORD OBSERVED', caption: 'We first see the record on May 14. The event date remains May 3.', spoken: 'Record observed May 14. Event occurred May 3. Not yet published.' },
    { mode: 'OBSERVATION PUBLISHED', caption: 'The May 16 release includes that observation, its source, and both earlier dates.', spoken: 'Published May 16. Observed May 14. Event occurred May 3.' }
  ];
  const days = ['03', '14', '16'];
  const notes = ['When it happened', 'When we first saw it', 'When we shared it'];
  let previous = 0;

  function setStage(value) {
    const stage = Math.max(0, Math.min(2, Number(value)));
    const state = states[stage];
    reader.dataset.stage = String(stage);
    reader.style.setProperty('--dial-turn', `${-52 + stage * 52}deg`);
    reader.style.setProperty('--advance', `${stage * 50}%`);
    control.value = String(stage);
    control.setAttribute('aria-valuetext', state.spoken);
    document.getElementById('window-mode').textContent = state.mode;
    document.getElementById('step-number').textContent = `0${stage + 1} / 03`;
    document.getElementById('explanation').textContent = state.caption;

    windows.forEach((window, index) => {
      const known = index <= stage;
      window.classList.toggle('is-known', known);
      window.classList.toggle('is-current', index === stage);
      window.classList.remove('arriving');
      window.querySelector('.day').textContent = known ? days[index] : '—';
      window.querySelector('.month').textContent = known ? 'MAY' : '—';
      window.querySelector('.date-note').textContent = known ? notes[index] : `Not yet ${index === 1 ? 'observed' : 'published'}`;
      if (known && index > previous) {
        requestAnimationFrame(() => window.classList.add('arriving'));
      }
    });
    buttons.forEach((button, index) => button.setAttribute('aria-pressed', String(index === stage)));
    previous = stage;
  }

  control.addEventListener('input', event => setStage(event.target.value));
  buttons.forEach(button => button.addEventListener('click', () => setStage(button.dataset.stage)));
})();
