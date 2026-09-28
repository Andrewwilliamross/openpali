# 04 — Signal

## Thesis

Make OpenPali read like a launch poster. Electric blue fills the screen; enormous white typography and a square-built P compete with confidence. A quiet field of squares brightens near the pointer. A small Together / Scattered button gives the field a second, keyboard-accessible state. The only destination is GitHub.

## Round one: initial composition

Built an actual Three.js instanced square field behind the full page. A deterministic pattern keeps the text area quiet and forms the P on the right. On mobile the P moves below the CTA. The field is an abstract identity device and never represents live records or recovery progress.

Inspected `qa-initial-desktop.png` at 1440 × 1000 and `qa-initial-mobile.png` at 390 px. The blue treatment has the strongest immediate campaign presence of these two concepts. The initial type spacing was cramped, the purpose was buried in the footer, and varied tile sizes made the assembled P noisier than necessary. The mobile mark sat too close to the footer rule.

## Round two: revision

- Loosened the large type's tracking.
- Put the plain project purpose directly beside the GitHub action.
- Made assembled P tiles uniform while preserving variation in the surrounding field.
- Moved the mobile P up for footer clearance.
- Removed repeated purpose copy from the footer.
- Replaced the fallback's dot pattern with actual square artwork and added the favicon.

This incorporates the editorial agent's peer critique about readable purpose and type spacing. Revised screenshots are `qa-desktop.png`, `qa-mobile.png`, `qa-interaction.png`, and `qa-fallback.png`.

## Current strengths

- The blue poster is recognizable at thumbnail size and naturally extends to social graphics.
- Uniform white squares make the P clear without an additional image request.
- Pointer illumination and the field toggle add play without interrupting reading or scrolling.
- Desktop and mobile compositions give the field different space while keeping the same hierarchy.
- The white GitHub CTA has a distinct segmented arrow treatment and visible keyboard focus.

## Current weaknesses

- The emphatic poster is less conversational than an editorial white page.
- The mark dominates the screen; the nearby purpose sentence is necessary for a first-time visitor.
- The field's optional interaction adds little factual understanding. It should remain decorative.
- This is particularly suited to a launch or campaign moment; a long-term documentation front door may benefit from a quieter visual treatment.

## Rendering cost and behavior

One instanced plane mesh holds a viewport-sized grid of squares. There are no lights, shadows, textures, or postprocessing passes. Pointer and focus changes update instance matrices and colors, so larger viewports mean more per-frame CPU work. DPR is capped at 1.5. Rendering stops when the field settles, becomes hidden, or leaves the viewport. Reduced motion disables pointer illumination and applies toggle changes immediately. Inline SVG and CSS provide the same complete blue poster if WebGL or the module is unavailable.

These are qualitative implementation characteristics. No timing, FPS, GPU, or battery measurements were collected.

## Verification

A headless Chrome run verified a live WebGL canvas, no page errors, the field toggle through Space, reduced-motion emulation, and no horizontal overflow at 390 px and 320 px. A separate JavaScript-disabled context rendered the headline, square P, and canonical GitHub action. Desktop, mobile, interaction, and fallback screenshots were captured; the desktop and mobile revisions were visually inspected. Results are in `qa-results.json`.

No square represents a person, property, statistic, or recovery judgment.
