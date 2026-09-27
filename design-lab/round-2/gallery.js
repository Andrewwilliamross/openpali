(() => {
  "use strict";
  const studies = {
    "field-office": {
      name: "Field Office",
      url: "../../dist/site/",
      status: "Recommended",
      medium: "Illustrated world · HTML/CSS",
      description:
        "Production candidate. A coastal paper world, a small field guide, and one invitation to GitHub.",
    },
    atlas: {
      name: "Living Atlas",
      url: "atlas/",
      status: "Interactive study",
      medium: "Three.js · live paper geometry",
      description:
        "Drag the landscape or use the fold slider. The paper reveals why event, observed, and published dates stay separate.",
    },
    instrument: {
      name: "Three Dates",
      url: "instrument/",
      status: "Interactive study",
      medium: "CSS instrument · interactive dates",
      description:
        "Advance the fictional record through a physical date reader. Native HTML/CSS and JavaScript; no WebGL.",
    },
    components: {
      name: "Components",
      url: "components/",
      status: "Working components",
      medium: "HTML/CSS · interface studies",
      description:
        "Try four invitations to GitHub, inspect an example source, and open a correction history.",
    },
  };
  const tabs = [...document.querySelectorAll("[data-study]")];
  const viewportButtons = [
    ...document.querySelectorAll("[data-viewport][aria-pressed]"),
  ];
  const frame = document.getElementById("study-frame");
  const panel = document.getElementById("study-panel");
  const stage = document.getElementById("stage");
  const shell = document.getElementById("viewport-shell");
  const announcement = document.getElementById("preview-announcement");
  const status = document.getElementById("study-status");
  let current = "field-office";
  let viewport = matchMedia("(max-width: 680px)").matches
    ? "mobile"
    : "desktop";
  let previousWidth = 0;

  function resizePreview() {
    const desktop = viewport === "desktop";
    const width = desktop ? 1440 : 390;
    const height = desktop ? 1000 : 844;
    const padding = getComputedStyle(stage);
    const available =
      stage.clientWidth -
      parseFloat(padding.paddingLeft) -
      parseFloat(padding.paddingRight);
    const scale = Math.max(0.1, Math.min(1, available / width));
    frame.width = width;
    frame.height = height;
    frame.style.width = `${width}px`;
    frame.style.height = `${height}px`;
    frame.style.transform = `scale(${scale})`;
    shell.style.width = `${width * scale}px`;
    shell.style.height = `${height * scale}px`;
    document.getElementById("viewport-size").textContent =
      `${width} × ${height}`;
  }

  function selectStudy(
    id,
    { focus = false, updateHash = true, announce = true } = {},
  ) {
    if (!Object.hasOwn(studies, id)) return;
    const study = studies[id];
    const changed = current !== id;
    current = id;
    tabs.forEach((tab) => {
      const selected = tab.dataset.study === id;
      tab.setAttribute("aria-selected", String(selected));
      tab.tabIndex = selected ? 0 : -1;
      if (selected && focus) tab.focus();
    });
    panel.setAttribute("aria-labelledby", `tab-${id}`);
    status.textContent = study.status;
    status.dataset.kind = id === "field-office" ? "recommended" : "study";
    document.getElementById("study-medium").textContent = study.medium;
    document.getElementById("study-description").textContent =
      study.description;
    document.getElementById("open-study").href = study.url;
    document
      .getElementById("open-study")
      .setAttribute("aria-label", `Open ${study.name} in a new tab`);
    frame.title = `${study.name} — live website preview`;
    if (changed) frame.src = study.url;
    if (updateHash && location.hash !== `#${id}`)
      history.replaceState(null, "", `#${id}`);
    if (announce)
      announcement.textContent = `${study.name} selected. ${study.medium}.`;
  }

  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => selectStudy(tab.dataset.study));
    tab.addEventListener("keydown", (event) => {
      let next;
      if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
      if (event.key === "ArrowLeft")
        next = (index - 1 + tabs.length) % tabs.length;
      if (event.key === "Home") next = 0;
      if (event.key === "End") next = tabs.length - 1;
      if (next === undefined) return;
      event.preventDefault();
      selectStudy(tabs[next].dataset.study, { focus: true });
    });
  });

  viewportButtons.forEach((button) =>
    button.addEventListener("click", () => {
      viewport = button.dataset.viewport;
      stage.dataset.viewport = viewport;
      viewportButtons.forEach((item) =>
        item.setAttribute("aria-pressed", String(item === button)),
      );
      resizePreview();
      announcement.textContent = `${studies[current].name}, ${viewport} preview.`;
    }),
  );

  window.addEventListener("hashchange", () =>
    selectStudy(location.hash.slice(1), { updateHash: false }),
  );
  window.addEventListener("resize", resizePreview);
  if ("ResizeObserver" in window) {
    new ResizeObserver((entries) => {
      const width = entries[0].contentRect.width;
      if (width !== previousWidth) {
        previousWidth = width;
        resizePreview();
      }
    }).observe(stage);
  }
  selectStudy(location.hash.slice(1) || "field-office", {
    updateHash: false,
    announce: false,
  });
  stage.dataset.viewport = viewport;
  viewportButtons.forEach((button) =>
    button.setAttribute(
      "aria-pressed",
      String(button.dataset.viewport === viewport),
    ),
  );
  resizePreview();
})();
