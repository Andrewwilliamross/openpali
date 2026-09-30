# Living Atlas — critique and implementation notes

## Thesis

A folded field atlas becomes a place. White hills, narrow canyon cuts, cobalt water, paper edges, and a blue bookmark give OpenPali a physical world. Opening its sheets reveals a real distinction in the project: an event date, an observation date, and a publication date answer different questions.

The coastline and relief are authored mathematical shapes. They contain no actual parcels, addresses, events, recovery measurements, or geographic claim.

## First screenshot review

`initial-desktop.png` and `initial-mobile.png` showed that the model, contour lines, and serif typography established a substantially different character from the monogram studies. The first scene was too small and left an excessive gap below the heading. The relief also needed gentler edges at the hinges so adjacent hills did not collide when folded.

## Second screenshot review and revision

`revised-desktop.png`, `revised-mobile.png`, `closed-desktop.png`, and `open-desktop.png` were inspected next. The larger atlas had useful presence, but its fully open tip approached the control and could be cropped.

The final revision:

- Enlarged the initial presentation and shortened the mobile scene area.
- Loosened the headline's letter spacing.
- Tapered relief toward each fold gutter.
- Reframed the camera from the articulated geometry's actual bounds, keeping the open and folded extremes inside the scene.
- Gave the control a separate, clear strip below the model.
- Simplified the static SVG's contour treatment and corrected its crop.

Final inspected captures: `desktop.png`, `mobile.png`, `closed.png`, `open.png`, and `fallback.png`.

## What is genuinely interactive

The Three.js scene has three physical paper panels in a hinge hierarchy. The middle hinge and the counter-fold of the last panel change together. Terrain, coastline, printed sheet labels, and bookmark belong to the panels and move with them. The camera fits their changing silhouette.

Drag horizontally on the scene or use the native range input. Home and End reach the folded and open states; arrow keys give smaller steps. The accompanying text distinguishes the three date meanings. There is one GitHub link, with `target="_top"` for gallery use.

The SVG fallback is a static geometric illustration. With JavaScript but no WebGL, the range changes the accompanying context and gently tilts that illustration; it does not reproduce the articulated WebGL model. With JavaScript disabled, the full composition, explanatory text, and GitHub action remain present.

## Authorship and medium

- `main.js` authors the live meshes, coastline, canyon height function, actual contour intersections, paper textures, hinges, bookmark, lights, shadows, and camera. It uses the existing local Three.js module.
- `make_poster.py` generates `poster.svg` from the same general coastal geometry using Python's standard library. Regenerate with `python3 design-lab/round-2/atlas/make_poster.py`.
- `styles.css` uses the project's locally bundled Fraunces and DM Sans fonts.
- This implementation is procedural Three.js and SVG. It does not claim a Blender or CAD export.

## Rendering behavior

The terrain uses three 42 × 48 grids: 12,096 terrain triangles, plus paper, walls, water, and the bookmark. Contour lines are computed once at construction. The paper textures are generated locally. A single directional shadow map is 1024 × 1024. DPR is capped at 1.5.

Frames run while a drag, slider change, or small pointer response settles; rendering stops at rest. Visibility and intersection handlers pause inactive rendering. Reduced motion removes pointer response and applies explicit fold changes immediately. These describe the implementation; no FPS, battery, or device performance claim is made.

## Verified behavior

See `qa-results.json` for the recorded Chrome run.

- Real WebGL canvas rendered without page errors.
- A direct mouse drag moved the range from 58 to 92 and exposed the release context.
- Home/End selected the source/release states and their matching date explanations.
- No horizontal overflow at 390 px or 320 px.
- The canonical GitHub href and top-level target were verified.
- Denying WebGL context creation kept the SVG and functional context control.
- Reduced-motion pointer movement requested no additional animation frames after settling; keyboard changes still worked.
- A JavaScript-disabled context retained the heading, fallback, and GitHub link.

## Remaining judgment

The atlas explains context more specifically than a rotating brand symbol. Its quiet tone and physical paper suit public evidence. The main Field Office's small character may provide more immediate warmth, while this alternative offers a more substantial interaction.

The relief is intentionally an illustrated object, not a physically manufacturable folding terrain model. On a phone, printed labels on the paper are decorative; the corresponding HTML explanations carry the meaning. Cross-browser testing, physical touch devices, full assistive-technology review, and hardware performance measurements remain outside this bounded pass.
