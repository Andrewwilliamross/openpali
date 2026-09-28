# The working notebook

Round three: a specific revision of the OpenPali landing page. Flat 2D drawing, actual local map geometry, and a pelican doing architectural fieldwork. This replaces the origami landscape and pointer parallax; it does not require another concept deck.

## The scene

**A pelican walks across an open field notebook, checks a parcel drawing against a source note, and traces an annotation into the margin.**

The notebook is the canvas. We look straight down at its page and read the drawing as a plan. The bird is a deliberately flat illustrated actor on that page. This small mismatch is part of the charm; perspective tricks and modeled paper would weaken it.

Use a close crop of actual Palisades parcels and streets. Keep its underlying geometry stationary. The animation gives the act of understanding a record personality. It does not animate a neighborhood's construction progress.

## What changes from the current page

The existing coastal sculpture established a character and a world, but the bird remained part of a still image. Pointer parallax moved the whole picture without giving the bird a task. This revision needs an observable sequence of decisions: arrive, inspect, compare, draw, leave.

The current page also spends much of its visual space on an imagined coastline. The new drawing should get close enough to see how streets, parcels, and annotations relate. Avoid replacing the sculpture with a distant blue map covered in tiny lines.

Keep the direct project description, one GitHub link, native field notes, and useful evidence semantics. Recompose the hero around the notebook instead of inserting a small animation into the old picture's box.

## Composition and drawing

### Desktop

- Let the notebook spread fill the hero. Its page edge, one margin rule, and a restrained binding detail establish paper without thickness, folded terrain, cast shadows, or a floating card.
- Reserve a clear text margin at the upper left. The actual plan occupies the center and right, extending toward the edge of the page. The drawing and its selected source note should be large enough to inspect.
- Start with roughly a dozen to a few dozen visible parcels and one or two readable street anchors, then let the available source determine the final crop. A dense overview of the entire recovery area will become wallpaper.
- Give the pelican a travel lane through open parts of the plan and the margin. Do not pass through the headline, GitHub action, source attribution, or motion control.
- Use white paper, cobalt drawing ink, dark text, and a pale blue secondary line. Parcel edges, street edges, and illustrative annotation need visibly different line weights. Avoid indiscriminate dashed lines and dimension marks.
- The bird should read through its silhouette: long bill and pouch, rounded white body, one cobalt wing shape, small eye, visible feet. Smooth ink shapes replace faceted origami geometry. One flat grounding line or ellipse is enough.

The construction-drawing character should come from accurate line hierarchy, an existing boundary being traced, a source leader, and careful annotation. Do not add fictional proposed houses, measured dimensions, or “approved” stamps to actual parcels.

### Mobile

Create a deliberate notebook crop. Keep the selected parcel group, source tab, drawing destination, and whole walking route in view. Simply shrinking the entire desktop scene would make both the feet and the map illegible.

At 390 px, aim for a bird about 85–110 px wide including its bill. Shorten the travel distance while retaining the same sequence and step count. Keep the project purpose and GitHub action above the scene. The notebook can continue below the fold; the invitation should not.

## A 26-second loop

Use this as the choreography, with small timing adjustments after watching the real rig. The page and camera remain still. There should be more purposeful looking than perpetual movement.

| Time | Action | What the viewer notices |
| --- | --- | --- |
| **0–2 s** | Pelican rests at the notebook margin, facing the drawing. Feet planted; one slow blink. Pencil is already part of the scene. | A complete first frame that makes sense before motion starts. |
| **2–7 s** | Six small alternating steps carry it toward a source callout. The body rolls slightly with each planted foot; the head stays steadier than the body. | It genuinely waddles. It does not slide across the page while its legs wiggle. |
| **7–10 s** | It stops fully, lowers the head toward the drawing, and makes one small comparison glance toward the source slip. | Inspection has a cause and a destination. The eye and beak point to the same relevant area. |
| **10–12 s** | Two short positioning steps bring the pencil tip to the start of a margin leader. The body settles before drawing. | Preparation gives the gesture weight. |
| **12–17 s** | With the pencil held in its bill, it traces a short leader from the existing drawing toward a notebook note. A brief corner tick finishes the stroke. The tip and ink remain synchronized. | The bird performs the architectural task. The trace connects record and context. |
| **17–19 s** | It lifts the pencil, straightens, and looks once between its annotation and the source. A restrained head tilt supplies the humor. | A small, completed piece of work. No celebratory badge or recovery milestone. |
| **19–24 s** | A planted turn, then six steps back along the clear margin route. The pencil travels with the bird or returns to its defined resting position. | The actor belongs to the page and knows where it is going. |
| **24–26 s** | It turns to the initial orientation, settles, and holds. | A clean seam into the next cycle, without teleporting or snapping. |

### Make the loop physically and logically continuous

The source geometry and a faint version of the annotation are present from the first frame. The bird's drawing pass adds a stronger temporary overstroke along that same annotation. During the return walk, the extra emphasis gently returns to its resting weight. The information stays intact; nothing appears to erase or revoke a public correction.

The last frame must match the first in position, orientation, pencil location, line emphasis, and pose. Use an actual drawn turn pose or a quick, intentional 2D turn while both feet are planted. A gradual `scaleX` transition through zero makes the character collapse; a 3D swivel breaks the medium.

## Motion direction for the rig

- **Foot contact leads the walk.** The planted foot stays in place relative to the page while the body passes over it. Swing the other foot forward, then exchange support. Match stride distance to body travel.
- **Keep the waddle modest.** A small side-to-side body roll and slight vertical movement are enough. Constant bouncing makes the bird look weightless.
- **Separate attention from locomotion.** Neck and head lead the inspection, then the body catches up. Wings mostly rest. Do not flap on every step.
- **Animate the drawing from the pencil tip.** Derive the ink reveal and pencil position from the same progress value. A decorative line appearing elsewhere would break the action.
- **Keep the bird on the page.** Do not clip its bill, pencil, feet, or turning pose at responsive boundaries. Check the entire route, not only the opening frame.
- **Use pauses as acting.** One comparison glance and one considered head tilt will create more individuality than constant blinking, cursor chasing, or random gestures.

## Controls and progressive enhancement

Provide a small, persistent native **Pause motion / Resume motion** button in the notebook margin, separate from the single outbound GitHub link. The label must describe the current available action. A click stops every part of the choreography at its current state: travel, legs, head, pencil, and ink. Resume continues from that same phase.

- Pause the animation clock when the page is hidden or the scene leaves view. Resume only if the visitor has not explicitly paused it.
- `prefers-reduced-motion` starts with a complete still: feet planted, the bird inspecting the note, and the finished annotation visible. There is no automatic walk or stroke animation. If an explicit “Play once” option is offered, make the opt-in clear and return to still mode afterward.
- JavaScript failure leaves the same useful static illustration, real text, native notes, and working GitHub link.
- Focus and hover should clarify controls, not start an unpredictable motion sequence. Do not make the bird follow the pointer or steal keyboard focus.
- Keep animated artwork out of the accessibility tree when its meaning is already provided by the figure description and field notes. Do not announce each phase through a live region.
- If field notes remain interactive, the selected note can emphasize the corresponding existing drawing detail. It must not force a jump in the walk cycle. Avoid simultaneously running three unrelated animations.

## Sparse copy

Keep the established hierarchy:

> **A place with footnotes.**
>
> Public evidence for the Palisades rebuild.
>
> **Explore on GitHub ↗**

One small notebook label can name the actual area or street shown once the source is chosen. One concise source line should distinguish the source-backed base drawing from the bird's illustrative annotations. Do not fill the scene with fake dossier labels to make it look technical.

Suggested motion-control text: **Pause motion**, **Resume motion**. Suggested short field note: **Follow the source.** Keep the rest of the existing explanation in the expandable notes or README.

## Geographic and product fidelity

The reference researcher is sourcing the real crop. Preserve its extent, projection, acquisition context, attribution, and export recipe. Simplify only with the original geometry available for comparison. The notebook does not need a live tile service to show a fixed, attributed plan.

If construction plans are included, they need their own source and reproduction basis. Architectural styling alone does not establish an approved design. A trace of an existing parcel edge or a separate, clearly illustrative margin sketch is safer than inventing a building inside a real parcel.

The actual product keeps [observations](../../pipeline/openpali/domain/observations.py) distinct from their projections and maintains parallel evidence lanes. The [methods page](../../web/src/pages/MethodsPage.tsx) preserves unknowns and conflicting sources. The animation should express inspecting and documenting; it should not resolve those questions by drawing a cheerful final state.

## Acceptance at implementation review

1. The unanimated composition reads as a flat notebook and close local drawing, with a clear purpose and GitHub link.
2. The bird takes visible, planted steps; it never travels while appearing to stand still.
3. Its gaze, source slip, pencil tip, and drawn line have a coherent spatial relationship.
4. A full 26-second viewing reveals one small task, rather than a collection of unrelated effects.
5. At the loop seam, no actor or tool teleports and no factual geometry changes.
6. Every action is contained at 320, 390, tablet, and desktop widths. No important label is obscured by the bird.
7. Pause stops the whole scene and resumes without a jump. Reduced motion and no JavaScript show a finished, meaningful still.
8. The real map and the illustrative action remain distinguishable, with a concise source note.

The motion can be implemented with a rigged SVG and a single shared timeline. Keep the base drawing static; animate only the actor, pencil, and annotation emphasis. Canvas or WebGL would add work without improving this specific flat composition.
