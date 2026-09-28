(() => {
  "use strict";
  const scene = document.getElementById("field-scene");
  const toggle = document.getElementById("motion-toggle");
  if (!scene || !toggle) return;

  const reduced = matchMedia("(prefers-reduced-motion: reduce)");
  const mobile = matchMedia("(max-width: 900px)");
  const part = (id) => scene.querySelector(`#${id}`);
  const rig = Object.fromEntries(
    [
      "pelican-position",
      "pelican-facing",
      "upper-body",
      "left-foot",
      "right-foot",
      "head",
      "eye",
      "notebook",
      "wing",
      "pencil",
      "pencil-stroke",
    ].map((id) => [id, part(id)]),
  );
  const scale = 1.23;
  const duration = 26;
  const startX = 300;
  const stopX = 610;
  const baseline = 795;
  const stroke = rig["pencil-stroke"];
  const strokeLength = stroke.getTotalLength();
  const strokeStart = stroke.getPointAtLength(0);
  let elapsed = 0;
  let previous = null;
  let frame = null;
  let inView = true;
  let paused = false;
  let playOnce = false;

  const clamp = (value) => Math.max(0, Math.min(1, value));
  const smooth = (value) => {
    const p = clamp(value);
    return p * p * (3 - 2 * p);
  };
  const windowProgress = (t, a, b) => smooth((t - a) / (b - a));
  const set = (name, value) => rig[name].setAttribute("transform", value);

  // The stance foot moves backwards by the body's exact forward travel.
  // During its shorter swing it lifts, returns, and meets the page again.
  function foot(name, phase, weight) {
    const p = ((phase % 1) + 1) % 1;
    const stride = ((stopX - startX) / 6.2 / scale) * 0.8 * 0.6;
    let x, y, angle;
    if (p < 0.6) {
      x = stride / 2 - (stride * p) / 0.6;
      y = 0;
      angle = 0;
    } else {
      const swing = (p - 0.6) / 0.4;
      x = -stride / 2 + stride * smooth(swing);
      y = -11 * Math.sin(Math.PI * swing);
      angle = -9 * Math.sin(Math.PI * swing);
    }
    x *= weight;
    y *= weight;
    angle *= weight;
    // The full rig faces the travel direction; local strides always face right.
    const pivot = name === "left-foot" ? "109 225" : "144 225";
    set(
      name,
      `translate(${x.toFixed(3)} ${y.toFixed(3)}) rotate(${angle.toFixed(3)} ${pivot})`,
    );
  }

  function render(seconds, still = false) {
    const t = seconds % duration;
    let x = startX;
    let facing = 1;
    let walking = false;
    let walkTime = 0;
    let phase = "resting";
    if (t >= 1 && t < 7.2) {
      x = startX + ((stopX - startX) * (t - 1)) / 6.2;
      walking = true;
      walkTime = t - 1;
      phase = "walking-out";
    } else if (t >= 7.2 && t < 18) {
      x = stopX;
      phase =
        t < 10
          ? "inspecting"
          : t < 12
            ? "lifting-pencil"
            : t < 16
              ? "drawing"
              : "checking-note";
    } else if (t >= 18 && t < 24.2) {
      x = stopX - ((stopX - startX) * (t - 18)) / 6.2;
      walking = true;
      walkTime = t - 18;
      facing = -1;
      phase = "walking-home";
    } else if (t >= 24.2 && t < 24.9) {
      facing = -1;
      phase = "turning-home";
    }
    if (still) {
      x = stopX;
      walking = false;
      facing = 1;
      phase = "still";
    }
    const originX = x - 130 * scale;
    const originY = baseline - 240 * scale;
    set("pelican-position", `translate(${originX.toFixed(3)} ${originY})`);
    set(
      "pelican-facing",
      facing < 0 ? `translate(${260 * scale} 0) scale(-1 1)` : "translate(0 0)",
    );
    let headAngle = 0,
      headX = 0,
      headY = 0;
    let penX = 0,
      penY = 0;
    const cycle = walkTime / 0.8;
    if (walking) {
      const settle = smooth(Math.min(walkTime / 0.18, (6.2 - walkTime) / 0.28));
      foot("left-foot", cycle, settle);
      foot("right-foot", cycle + 0.5, settle);
      const turnSettle = t >= 18 ? 1 - windowProgress(t, 18, 18.25) : 0;
      const bob =
        -1.7 * Math.cos(cycle * Math.PI * 4) * settle + 3 * turnSettle;
      const roll = 1.7 * Math.sin(cycle * Math.PI * 2) * settle;
      set(
        "upper-body",
        `translate(0 ${bob.toFixed(3)}) rotate(${roll.toFixed(3)} 130 210)`,
      );
      headAngle = -roll * 0.65;
    } else {
      set("left-foot", "translate(0 0)");
      set("right-foot", "translate(0 0)");
      set("upper-body", "translate(0 0)");
      if (t >= 7.2 && t < 10)
        headAngle = 9 * Math.sin(((t - 7.2) / 2.8) * Math.PI);
      if (t >= 10 && t < 18 && !still) {
        const pickup =
          windowProgress(t, 10, 11.6) * (1 - windowProgress(t, 16.3, 17.4));
        headAngle = 12 * pickup;
        penX = 65 * pickup;
        penY = -31 * pickup;
        const progress = clamp((t - 12) / 4);
        const point = stroke.getPointAtLength(strokeLength * progress);
        const drawingWeight =
          t < 16.3 ? pickup : 1 - windowProgress(t, 16.3, 17.4);
        headX = ((point.x - strokeStart.x) / scale) * drawingWeight;
        headY = ((point.y - strokeStart.y) / scale) * drawingWeight;
        penX += headX;
        penY += headY;
      }
      if (!still) {
        // Anticipation and a planted beat make the quick 2D direction change read as a turn.
        let turn = 0;
        if (t >= 17.4 && t < 18) {
          turn = windowProgress(t, 17.4, 18);
          phase = "turning-back";
        }
        if (t >= 24.2 && t < 24.9) turn = windowProgress(t, 24.2, 24.9);
        if (t >= 24.9 && t < 25.25) turn = 1 - windowProgress(t, 24.9, 25.25);
        if (turn > 0) {
          headAngle = -12 * turn;
          set(
            "upper-body",
            `translate(0 ${3 * turn}) rotate(${-2 * turn} 130 210)`,
          );
        }
      }
      if (still) headAngle = 5;
    }
    set(
      "head",
      `translate(${headX.toFixed(3)} ${headY.toFixed(3)}) rotate(${headAngle.toFixed(3)} 139 138)`,
    );
    set("pencil", `translate(${penX.toFixed(3)} ${penY.toFixed(3)})`);
    set("notebook", "translate(0 0)");
    set("wing", "translate(0 0)");
    const blinkClock = t % 6.3;
    const eyeOpen = !still && blinkClock > 5.95 && blinkClock < 6.11 ? 0.13 : 1;
    set("eye", `translate(153 65) scale(1 ${eyeOpen}) translate(-153 -65)`);
    const ink = still ? 1 : clamp((t - 12) / 4);
    stroke.style.strokeDasharray = "1";
    stroke.style.strokeDashoffset = String(1 - ink);
    stroke.style.opacity = String(still ? 1 : 1 - windowProgress(t, 20, 24));
    scene.dataset.phase = phase;
    scene.dataset.time = seconds.toFixed(3);
  }

  function updateButton() {
    const stopped = paused || (reduced.matches && !playOnce);
    toggle.querySelector(".motion-label").textContent =
      reduced.matches && !playOnce
        ? "Play once"
        : stopped
          ? "Resume motion"
          : "Pause motion";
    toggle.querySelector(".motion-icon").textContent = stopped ? "▷" : "Ⅱ";
  }
  function running() {
    return (
      !paused && !document.hidden && inView && (!reduced.matches || playOnce)
    );
  }
  function tick(now) {
    frame = null;
    if (!running()) {
      previous = null;
      return;
    }
    if (previous !== null) elapsed += Math.min(now - previous, 100) / 1000;
    previous = now;
    if (playOnce && elapsed >= duration) {
      playOnce = false;
      elapsed = 0;
      previous = null;
      render(0, true);
      updateButton();
      return;
    }
    render(elapsed);
    frame = requestAnimationFrame(tick);
  }
  function sync() {
    if (frame !== null) cancelAnimationFrame(frame);
    frame = null;
    previous = null;
    if (running()) frame = requestAnimationFrame(tick);
  }
  function responsive() {
    scene.setAttribute(
      "viewBox",
      mobile.matches ? "10 0 940 850" : "0 0 1100 850",
    );
  }
  toggle.addEventListener("click", () => {
    if (reduced.matches && !playOnce) {
      elapsed = 0;
      playOnce = true;
      paused = false;
    } else paused = !paused;
    updateButton();
    sync();
  });
  reduced.addEventListener("change", () => {
    playOnce = false;
    elapsed = 0;
    paused = false;
    render(0, reduced.matches);
    updateButton();
    sync();
  });
  mobile.addEventListener("change", responsive);
  document.addEventListener("visibilitychange", sync);
  if ("IntersectionObserver" in window) {
    new IntersectionObserver(
      (entries) => {
        inView = entries[0].isIntersecting;
        sync();
      },
      { threshold: 0 },
    ).observe(scene);
  }
  document.querySelectorAll('[name="field-note"]').forEach((note) => {
    note.addEventListener("toggle", () => {
      if (note.open) {
        document.querySelectorAll('[name="field-note"]').forEach((other) => {
          if (other !== note) other.open = false;
        });
        document.body.dataset.note = note.dataset.note;
      } else if (document.body.dataset.note === note.dataset.note)
        delete document.body.dataset.note;
    });
  });
  responsive();
  render(0, reduced.matches);
  toggle.hidden = false;
  updateButton();
  sync();
})();
