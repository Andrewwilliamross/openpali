# Design lab QA

> Archived first exploration. See [Round 2](round-2/README.md) for the current Field Office direction and live gallery.

## Scope

A bounded local audit in headless Google Chrome through Playwright. The gallery and component labs were checked at 1440 × 1000 and 390 × 844. Assembly and Signal were also checked for horizontal overflow at 320 px. This record describes tested behavior, not a full accessibility or performance certification.

Machine-readable evidence: [qa-results.json](qa-results.json). Concept-specific screenshots and notes remain in [Assembly](concepts/03-assembly/critique.md) and [Signal](concepts/04-signal/critique.md).

## Passed

- **Gallery:** all six thumbnails loaded. Overview → Assembly/Signal → 390 px Mobile preview → Overview works. Returning removes the iframe source. Desktop and mobile layouts had no horizontal overflow.
- **Keyboard focus:** Enter on the Assembly card focuses “Show Assembly” in the chooser. Returning to Overview focuses the Assembly card. A fresh Signal deep link opens its viewer without forcing focus. The mobile Aperture chooser remained visible after selection.
- **GitHub action:** Assembly and Signal have the canonical repository URL and `target="_top"` inside the gallery. The audit checked these attributes without navigating away to GitHub.
- **Button lab:** Rest, Hover, Focus, and Press set the intended preview state; one state button remains pressed and all eight link examples remain present. Hover color and the simulated focus outline were checked.
- **Evidence tabs:** Right/Left arrows wrap correctly; Home/End select the first/last tab. Focus, selected state, panel label, content, and the single tab stop stay synchronized.
- **Assembly/Signal controls:** keyboard Home/End operates the assembly slider; Space operates the field toggle. Both render real WebGL canvases. No page errors were observed in the audited flows.
- **Reduced motion:** both canvases rendered with the media preference enabled. Pointer movement requested no additional animation frames after settling; explicit controls still worked.
- **No WebGL:** canvas WebGL context creation was deliberately denied while JavaScript remained enabled. Both inline fallbacks rendered. Assembly's slider changed the SVG cube positions; Signal's toggle changed its fallback state.
- **No JavaScript:** separate browser contexts rendered each concept's heading, inline identity, and GitHub action.

## Corrections verified

The audit found and fixed two integration issues: Assembly/Signal links originally navigated their iframe, and opening a concept by keyboard lost focus. The top-level link targets and gallery focus restoration were rechecked after correction. Existing review screenshots were not replaced during this audit.

## Remaining limits

- Browser coverage is Chrome only. Safari, Firefox, physical phones, touch-only behavior, screen readers, forced colors, and every contrast combination have not received a complete audit.
- Rendering behavior was checked qualitatively. FPS, frame timing, GPU cost, memory, battery usage, and slow-network performance were not benchmarked.
- The detailed WebGL, fallback, and reduced-motion checks apply to concepts 03 and 04. They do not certify every effect in the other four concepts.
- This audit does not validate Blender/CAD geometry, production deployment, or external GitHub navigation.

Additional fallback and reduced-motion capture evidence is retained locally in `/private/tmp/openpali-final-audit/`.
