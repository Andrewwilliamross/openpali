# OpenPali design studies

> Archived first exploration. See [Round 2](round-2/README.md) for the current Field Office direction and live gallery.

Six working visual directions, eight button treatments, and a small evidence-component lab. Start with the [interactive gallery](index.html), then read the [design review](REVIEW.md).

These are alternatives for review. The existing [`site/`](../site/README.md) remains the current project website; a study does not become production automatically.

## Run locally

From the repository root, using Python 3:

```sh
python3 -m http.server 4173 --bind 127.0.0.1
```

Open [the gallery](http://127.0.0.1:4173/design-lab/). Serve the repository root so shared assets and JavaScript modules resolve correctly. No npm install or platform services are needed to view the studies.

| Study | Local page | Try |
| --- | --- | --- |
| 01 · Fieldnotes | [Editorial cover](http://127.0.0.1:4173/design-lab/concepts/01-fieldnotes/) | Open and close the margin note. |
| 02 · Ledger | [Evidence sheets](http://127.0.0.1:4173/design-lab/concepts/02-ledger/) | Change the active tab and unfold the layers. |
| 03 · Assembly | [Modular P](http://127.0.0.1:4173/design-lab/concepts/03-assembly/) | Pull the cubes apart, then bring them together. |
| 04 · Signal | [Cobalt poster](http://127.0.0.1:4173/design-lab/concepts/04-signal/) | Switch between the gathered mark and scattered field. |
| 05 · Material | [Rendered sculpture](http://127.0.0.1:4173/design-lab/concepts/05-material/) | Move a fine pointer to see the image shift against the type. |
| 06 · Aperture | [Optical still](http://127.0.0.1:4173/design-lab/concepts/06-aperture/) | Inspect the split glass button and its focus state. |
| Button lab | [Eight invitations](http://127.0.0.1:4173/design-lab/components/) | Compare rest, hover, focus, and pressed previews. |
| Component lab | [Evidence interface](http://127.0.0.1:4173/design-lab/components/evidence.html) | Open disclosures and use the keyboard tabs. |

The landing concepts each have one GitHub link. The button lab deliberately repeats that destination to compare treatments. Interface records are illustrative, and decorative squares do not represent recovery progress.

## What is actually being rendered

| Mechanism | Studies | Dependencies and provenance |
| --- | --- | --- |
| Native HTML/CSS | Fieldnotes, Ledger, component labs | System fonts and local JavaScript. Ledger uses CSS perspective, explicit stacking order, and a depth slider. |
| Live WebGL | Assembly, Signal | Local **Three.js 0.186.1** modules under [`vendor/three/`](vendor/three/), with the upstream [MIT license](vendor/three/LICENSE). Original scene code; inline SVG/CSS fallbacks remain available if WebGL fails. |
| Rendered image with alpha | Material | Original Blender **5.2.2** geometry and Cycles render. Editable [`scene.py`](assets/material/scene.py) and [`.blend`](assets/material/openpali-material.blend), plus transparent/studio PNGs. Browser motion is image parallax; lighting is baked in. |
| Generated image | Aperture | Original OpenAI ImageGen output from this session, saved as [`aperture.png`](assets/generated/aperture.png). It is an abstract material image, not a photograph, a Blender render, or live 3D. Prompt/provenance is in the [concept critique](concepts/06-aperture/critique.md). |

There are no downloaded fonts or required CDN requests. Blender and ImageGen are authoring tools; visitors do not need either. To reproduce Material, follow its [render instructions](concepts/05-material/critique.md#reproduce). The checked-in Three package metadata records its version; only the required module files are vendored.

Official technical references: [Three.js documentation](https://threejs.org/docs/), [Blender Python API](https://docs.blender.org/api/current/), and the [official Blender Python package](https://pypi.org/project/bpy/). The original Omarchy, Prime Agent, and GeoLibre research is in [the brand reference study](../Docs/Brand/REFERENCES.md).

## Review artifacts

- `concepts/*/critique.md` records each author's rationale, limits, and revisions. Assembly and Signal also include `qa-results.json` with their browser checks.
- Concept folders and `output/design-review/screenshots/` contain review captures; the live pages show interactions that a screenshot cannot.
- Completed 18-slide presentation: `output/design-review/OpenPali-Design-Review-Edition-01.pptx` from the repository root. This is the review deck, separate from website deployment.

The main comparison sizes are 1440 × 900 and 390 × 844. Assembly, Signal, and Material also have author captures at 1440 × 1000; some mobile compositions scroll vertically. Browser, keyboard, motion, and fallback evidence should be recorded with its actual scope; a screenshot is not a production performance test.

## Verification

[QA.md](QA.md) and [qa-results.json](qa-results.json) record the checked gallery flows, keyboard controls, responsive layouts, reduced motion and actual WebGL-denied fallbacks. Final slides were rendered and visually reviewed; native PowerPoint execution was not tested.

## Before choosing a direction

See [REVIEW.md](REVIEW.md) for the provisional synthesis and the remaining implementation checklist. The project owner's choice determines the final composition. Code licensing is still pending; the vendored Three.js license does not grant rights to the rest of OpenPali. Existing source-data and imagery terms remain separate.
