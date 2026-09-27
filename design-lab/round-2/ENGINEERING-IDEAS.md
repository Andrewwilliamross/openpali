# Round 2 — a place, a story, a useful object

## Recommendation

Develop **The Coastal Field Table**. Make a memorable place where someone is patiently making sense of a complicated public record. The hero should be an authored scene with a small story already happening when the page opens.

The strongest image is an open notebook on a white coastal bluff, cobalt water beyond it, and an original folded-paper shorebird lifting a tracing sheet. The note under that sheet is the important discovery. The bird gives the work personality; the coast makes it OpenPali; the paper makes its evidence purpose tangible.

A lighthouse is an interchangeable guidance symbol. Tiny rebuilt houses could be mistaken for a reconstruction model. A giant monogram explains little. The field table has more specific work to do.

## Grounding in the actual project

- [README](../../README.md): public evidence for the rebuild after the January 2025 Palisades Fire; claims should lead back to sources.
- [Parallel evidence lanes](../../pipeline/openpali/domain/lanes.py): cleanup, design review, permitting, construction, and occupancy have separate evidence. Their meaning should survive the illustration.
- [Temporal semantics](../../pipeline/openpali/domain/temporal.py): unknown dates remain unknown. Observation time and occurrence time differ.
- [Methods UI](../../web/src/pages/MethodsPage.tsx): missing public evidence does not establish inactivity; source conflicts remain visible.
- The Palisades belongs to a coastal and mountainous setting. That supports a visual vocabulary of sea, relief, and folds. Use an authored landscape rather than an unlabeled geographic reconstruction. [Los Angeles City Planning community plan](https://planning.lacity.gov/odocument/abf34149-0480-4d2d-9506-26b8e06fe185/Brentwood-Pacific_Palisades_Community_Plan.pdf)

[Cua](https://cua.ai/) is useful as a reference for committing to a coherent world and character. Its computer landscape and character belong to its own story. OpenPali needs a world made from its place, materials, and work.

---

## 1. The Coastal Field Table — recommended

### Thumbnail in words

A wide white page, almost like the opening spread of an illustrated field guide. A calm, dark headline sits in the upper left; the wordmark is small. Across the lower right, a thick sheet of white paper becomes a shallow coastal bluff. Its cut edge has fine contour lines. A cobalt sea curves around it and continues beyond the crop. On the bluff is a small open notebook held flat by a blue survey pencil. One sheet is translucent. A distinctive little shorebird, made from two or three crisp folded-paper planes, has caught its corner in its beak. Under the lifted sheet is a blue source note and a thin connecting rule. A tiny curl in the sea and an imperfect pencil underline give the scene warmth. Nothing forms a letter.

**Proposed headline:** “The rebuild, in view.”

**Purpose line:** “Public evidence for the Palisades rebuild.”

**Primary action:** “Explore on GitHub.”

### Story and interaction

The bird is curious about the record. Hovering or focusing the paper corner lifts it slightly and reveals the source note. A click, tap, or Enter settles it into the open position; the same action closes it. The content remains readable in its resting composition. The character does one small, authored action instead of following the cursor around the page.

The paper should reveal a source label, not an invented permit, date, address, or progress state. A tiny “Illustrative field note” label can live on the artwork's paper edge. The plain project description remains outside the art.

### Medium and architecture

**Best shipping route:** an original Blender still with separately rendered paper corner, bird, shadow, and source-note layers. A small CSS hinge and SVG connector produce the interaction. The artwork is always present before JavaScript. No WebGL is needed for this version; there is no benefit in paying for a full engine to tilt a static scene.

The Blender file contains the complete scene and cameras, not just a texture pasted on a plane. Save the source generator and editable `.blend`. Prepare a desktop composition and a mobile crop from the same scene. Keep important typography in HTML; place only tiny artistic labels in the render.

If a later art test proves that perspective rotation is essential, export the bird and paper as a small GLB over the fixed background. That is an optional enhancement, not a reason to reduce first-frame quality.

### Performance shape

A compressed responsive hero image plus three or four small overlay assets. Pointer input changes CSS custom properties only while the pointer is over the paper; reduced motion switches between still open/closed states. Hidden tabs do no work. No looping water, particles, audio, or cloth simulation.

**Production risk:** layer registration and convincing shadow movement. Solve these with fixed cameras and a deliberately small fold angle. Large rotations would expose the baked illusion.

### Why it can become a project identity

The bird, pencil underline, contour edge, and source-note tab provide a family of useful motifs. A GitHub banner shows the whole field table. A social crop centers the bird and the lifted note. An avatar uses the bird's silhouette. Release graphics reuse the notebook's small tab and blue rule. The shared story survives each crop.

---

## 2. The Living Paper Atlas

### Thumbnail in words

An oversized white accordion map lies diagonally across a cobalt tabletop. One end is still folded into a compact, tactile book; the other opens into a white coastal ridge. Contour lines run over the folds and end at the sea. Three different sheets are visible: opaque paper, a translucent observation sheet, and a narrow source slip tucked into the binding. A blue fabric bookmark follows the spine and exits into the margin near the GitHub link. The main headline sits above the quiet closed end of the atlas. One small paper shorebird can rest on the book's corner, but the object works without it. This is a book becoming a place, not a set of floating interface panels.

**Proposed headline:** “A place. A record. A clearer picture.”

### Story and interaction

Opening a fold reveals the context behind a visible line. The visitor can unfold one section and refold it. Source, observation, and published snapshot are visibly different sheets, not a progress ladder. Printed labels remain modest. There is no before/after rebuilding animation and no claim that opening paper uncovers hidden facts about a property.

### Medium and architecture

This is the best candidate for **real Three.js**. Model the atlas in Blender as rigid paper panels joined by named hinges. Export its low-poly geometry and baked lighting/material atlas. Animate the hinges through a bounded state machine; do not run a fabric solver. A native range or two-state button controls the same parameter as a drag gesture. Keyboard interaction is first-class.

A Blender render of the fully composed starting state is the initial image and fallback. Load the local Three.js module and GLB after interaction or when the hero is clearly visible. The live scene must match that still closely enough that enhancement does not cause a visual jump. Use an orthographic or long-lens camera and limit free rotation.

### Performance shape

Suggested starting budgets, to be measured after a model exists: below 40,000 visible triangles; roughly 8–12 draw calls; one 1024 px material atlas, with a larger desktop option only if it visibly helps; DPR capped at 1.5. Baked shadows and ambient occlusion replace real-time shadow passes. Render during hinge movement and settling, then stop. Reduced motion uses immediate stable fold states. A context failure keeps the complete still and the same GitHub link.

**Production risk:** believable folded-paper topology, avoiding intersections, and matching a live scene to the carefully lit still. This direction needs the most engineering to reach the promised visual finish.

### Identity potential

The accordion edge, blue bookmark, and unusual coastal fold create recognizable crops without any monogram. Documentation diagrams can reuse the three sheet types. It has the clearest physical metaphor for context, but a weaker character presence than the field table.

---

## 3. The Community Proofing Bench

### Thumbnail in words

A compact white proofing press sits on an open workbench. Its rollers and hand crank are cobalt; its edges have subtle wear rather than futuristic gloss. A broad paper ribbon passes through it. At the left, two modest source sheets sit slightly out of registration under a blue metal clip. At the right, a single sheet emerges carrying a delicate coastal contour and a visible source trail along its margin. A small stack of saved sheets remains beside the press. The paper continues out of the hero crop, as if more people could join the table. The press is clearly a handmade editorial object, not an industrial factory or a fake application screenshot.

**Proposed headline:** “Make the record clear.”

### Story and interaction

A short turn of the crank aligns the two translucent source sheets and advances one printed sheet. The original sheets remain in view. The meaningful gesture is bringing sources into a readable record while preserving them. It does not mark a claim “verified,” erase a conflict, or produce a fictional property report.

One restrained detail supplies the fun: the blue clip rocks and settles when the paper advances. This world already has a protagonist—the press—so a mascot would add clutter.

### Medium and architecture

Author the complete press, paper, clips, and lighting in Blender. Render a static master plus separated crank and paper layers. CSS transforms move the crank; a masked paper layer advances through the stationary body. The scene needs a fixed camera, so layered compositing can achieve a polished result without a runtime renderer. An SVG source trail can animate along the margin, tied to the same action.

A GLB would only be justified if the visitor needs to inspect the press from a second angle. The proposed story does not need that feature.

### Performance shape

The initial load is a responsive image. The crank and paper animate only after an intentional action; there is no continuous conveyor. Reduced motion swaps between the two final frames. The image remains complete when JavaScript is missing. Use real text beside the art to explain the platform; the press is a metaphor, not a claim that a report-export feature has shipped.

**Production risk:** the illustration could suggest a publishing company. Coastal contours, retained source sheets, and the direct Palisades purpose sentence must be prominent. Its personality is strong, but its sense of place is less immediate than the field table.

---

## Feasibility with the current workspace

- An authored Blender example, saved scene, transparent render, and studio render already exist at `design-lab/assets/material/`. Its [scene.py](../assets/material/scene.py) uses `bpy`, Cycles, procedural geometry, and original materials. This is a starting point for the authoring workflow, not geometry to reuse in the new world.
- The Python 3.13 Blender environment is on disk at `/private/tmp/openpali-bpy/`; `bpy` is installed there. No new installation is required for the proposed authoring path. This round inspected the existing environment and source; it did not render a new scene.
- Local Three.js is already available. Measured file sizes: `three.module.js` is 662,772 bytes and `three.core.js` is 1,458,113 bytes. Python gzip compression of those files totals 417,288 bytes before scene assets. That is a useful reason to make its presence earn a real interaction. These are file measurements, not browser transfer or execution benchmarks.
- The official Three.js package already unpacked under `/private/tmp/openpali-three/` includes `GLTFLoader`, `BufferGeometryUtils`, and `SkeletonUtils`. A GLB route would need those dependencies vendored with compatible local imports. They have not been added during this proposal round.

## What “95% ready” should mean for the selected world

1. Approve the whole composition at desktop and mobile sizes before polishing isolated props.
2. Author the actual objects, materials, paper edges, lighting, and shadows. Keep an editable scene and repeatable export command.
3. Produce the final first frame, a deliberate mobile composition, and one meaningful interaction. The GitHub CTA must be immediately readable and reachable.
4. Verify keyboard use, reduced motion, the image-only fallback, gallery embedding, and realistic load behavior. Measure bytes and rendering work before claiming performance.
5. Finish the same world as a GitHub banner, social preview, square crop, small avatar, and release-note motif. The selected scene should supply a coherent family, not a collection of unrelated effects.

**Decision:** select the Coastal Field Table for its specific place, inspectable source note, and original small character. Use the Living Paper Atlas if a genuine three-dimensional interaction is the priority. Keep the Proofing Bench as a distinct alternative with an editorial, communal personality.

No scene, site, or production asset has been implemented in this round. This file is the proposal and engineering assessment.
