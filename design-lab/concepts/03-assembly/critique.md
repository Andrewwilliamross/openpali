# 03 — Assembly

## Thesis

Let the identity behave like something people can build together. A white studio, oversized ink typography, and a blue P made of physical cubes create a playful invitation. One GitHub action stays visually primary. The range control is a small, optional toy with a clear cause and effect.

## Round one: initial composition

Built a real Three.js scene with fifteen instanced cubes, perspective, studio lighting, cast shadows, gentle pointer parallax, and a pull-apart / bring-together slider. The opening scene is still. Inline SVG cube art is present before the module loads.

Inspected `qa-initial-desktop.png` at 1440 × 1000 and `qa-initial-mobile.png` at 390 px. The mark has useful scale, the CTA reads immediately, and the mobile scene keeps the slider and footer in a comfortable vertical flow. The first headline tracking was too tight. “Open tools for a clearer picture” was less precise than the project's actual purpose and could suggest a license promise. The footer alone was too quiet a place to explain the project.

## Round two: revision

- Put “Public evidence for the Palisades rebuild” directly below the headline.
- Loosened headline tracking on desktop and mobile.
- Added descriptive `aria-valuetext` for the assembly slider.
- Added the project favicon and cleaned a redundant camera expression.
- Kept the initial assembled state quiet; motion follows the visitor's actions.

This incorporates the editorial agent's peer critique about purpose and licensing language. Revised screenshots are `qa-desktop.png`, `qa-mobile.png`, `qa-interaction.png`, and `qa-fallback.png`.

## Current strengths

- The interaction explains itself: moving the slider separates the identity and restores it.
- Genuine lighting and shadows give the square system a physical character.
- The slider works with Home, End, and arrow keys; focus is visible.
- The illustration remains substantial and recognizable without JavaScript or WebGL.
- The main action links directly to the canonical repository.

## Current weaknesses

- The abstract identity needs the purpose sentence to connect it to public evidence.
- The cubes look intentionally geometric. A carefully rendered material study may feel more tactile in a still image.
- The full mobile composition scrolls; it favors a readable CTA and useful interaction over fitting everything into one viewport.
- The compressed default system type remains a design choice that should be judged alongside the quieter editorial concepts.

## Rendering cost and behavior

One instanced cube mesh shares geometry and material; a second plane receives the shadow. The directional shadow map adds a rendering pass. DPR is capped at 1.65. The renderer requests frames while an interaction settles and stops at rest. Visibility and intersection observers stop work when the scene is inactive. Reduced motion removes pointer parallax and interpolation. The range control can manipulate the inline fallback when the Three.js module is unavailable.

These are implementation characteristics, not measured performance claims. No FPS, GPU-time, battery, or device benchmarking was performed.

## Verification

A headless Chrome run verified a live WebGL canvas, no page errors, keyboard control, reduced-motion emulation, and no horizontal overflow at 390 px and 320 px. A separate JavaScript-disabled context rendered the heading, SVG identity, and canonical GitHub action. Desktop, mobile, exploded, and fallback screenshots were visually inspected. Results are in `qa-results.json`.

The artwork is abstract. It depicts no parcels, people, progress, or evidence quality.
