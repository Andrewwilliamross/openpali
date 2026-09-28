# 05 — Material / piece by piece

## Design argument

Give the open square physical weight. Eleven cobalt acrylic tiles rest on
porcelain and clear optical spacers; the twelfth tile sits just outside the
ring. The composition treats contribution as careful assembly. The object is
abstract: its tiles do not count homes, parcels, events, or recovery progress.

The landing page borrows the hierarchy of a small design exhibition. A quiet
masthead establishes the name. Oversized blue typography sits behind the
transparent render. The object interrupts the letters, while the complete name
remains in the masthead. A compact invitation and one GitHub action anchor the
lower left. There are no invented metrics or fictional product screenshots.

## Software and provenance

- Original geometry, materials, studio lighting, and composition built with
  **Blender 5.2.2**, using the official `bpy==5.2.2` Python package.
- Installed only into an isolated temporary environment at
  `/tmp/openpali-bpy`; repository dependencies were not changed.
- Rendered with **Cycles**, 144 samples, denoising, and AgX color management.
- No generated-image service, downloaded models, textures, stock assets, or
  external HDRIs were used for the sculpture.
- Material source blue is `#1557FF`. Physically rendered reflections and AgX
  change its apparent color; CSS uses the exact blue.
- Transparent and studio PNGs are 1600 × 1300. The `.blend` file and `scene.py`
  preserve the editable setup.

The official package and version compatibility are documented on
[Blender's PyPI page](https://pypi.org/project/bpy/).

## Browser construction

- The render is an image at `z-index: 3`, ahead of the main wordmark at
  `z-index: 1`. The invitation remains above both at `z-index: 5`.
- Fine pointers move the artwork by at most seven horizontal and five vertical
  pixels. This is deliberate image parallax, not interactive 3D or live
  relighting. The studio lighting is baked into the render.
- Motion is disabled for reduced-motion preferences and coarse pointers.
- The page works with JavaScript disabled. The only link opens the canonical
  GitHub repository. Image alternative text describes the sculpture.

## Tradeoffs

**Strengths:** A distinctive silhouette with real optical depth; an asset that
can work across a website, social card, release cover, or event slide; low
browser processing cost; a reproducible material system.

**Limits:** The image is heavier than vector artwork. Its neutral glass
refractions are baked in, so placing it over a new background does not produce
physically accurate transmission of the typography behind it. The sculpture
communicates care and openness more clearly than it communicates the actual
evidence workflow. A full project README must supply that detail.

**Next iteration:** Try one fewer material layer, stronger cobalt absorption,
and a closer crop. Review whether the disconnected tile reads as an invitation
or merely a missing part. A live WebGL version could expose material changes,
but should justify its larger runtime and motion budget.

## Reproduce

With Blender 5.2.2 installed:

```sh
blender --background --python design-lab/assets/material/scene.py
```

Or with Python 3.13 and the official module in an isolated environment:

```sh
python -m pip install bpy==5.2.2
python design-lab/assets/material/scene.py
```

Use `--preview` for the lower-resolution 32-sample draft. On this machine the
sandboxed Blender import crashed; the same scene completed when granted host
access. Reproduction may therefore require normal host execution rather than a
restricted subprocess sandbox.

## Verification

- Both final Blender renders were opened and visually inspected. Lighting was
  revised after the first draft to retain a richer cobalt color.
- Browser screenshots inspected at 1440 × 900 and 390 × 844; saved here as
  `desktop.png` and `mobile.png`. The CTA, descriptive copy, and project name
  remain visible at both widths.
- JavaScript syntax and whitespace checks passed.
- The initial browser console showed a missing default favicon only; an
  explicit link to the local SVG mark was added.
- The object annotation was moved below the detached tile after checking the
  shorter desktop viewport, so the two no longer overlap.
