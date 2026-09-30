# The field-note pelican

An original, flat SVG character: a curious pelican carrying a small paper field notebook. It faces right, with a long cobalt bill, soft pouch, white body, blue wing, and two separate webbed feet. Its quiet expression and practical notebook make it a field observer rather than a mascot performing for the viewer.

## Source

`assets/brand/field-notes-2d/pelican.svg` — editable path geometry, transparent background, `viewBox="0 0 260 260"`. No raster images, fonts, filters, gradients, or baked animation. The notebook’s blank label remains readable as a paper insert without miniature text.

The palette is cobalt `#1557ff`, ink `#183554`, warm white `#fffef9`, and pale blue. Rounded curves and small variations in the ink line replace the previous folded-paper geometry. Flat accents describe the pouch and feathers; there is no perspective or cast shadow.

## Animation hooks

Inline the SVG to animate the semantic groups. Preserve the drawing order: feet, body, head, notebook, pencil, wing. The near wing passes in front of the notebook so the bird visibly holds it. A slim pencil rests beside the notebook and can move to the bill for an annotation.

| Group | Suggested pivot | Purpose |
| --- | --- | --- |
| `#left-foot` | `109 205` | Far foot; short alternating step |
| `#right-foot` | `144 205` | Near foot; settles on the baseline |
| `#body` | `135 155` | Main torso; subtle walking bob |
| `#head` | `139 138` | Neck and head; a small curious tilt |
| `#eye` | `153 64` | Blink; nested inside head |
| `#bill` | inherited head motion | Bill and soft pouch |
| `#notebook` | `155 171` | Held paper notebook |
| `#pencil` | `195 186` | Separate drawing prop, pivot at graphite tip |
| `#wing` | `105 154` | Near wing, clasped around the notebook |

The SVG contains matching `transform-origin` declarations and `data-pivot` attributes. `#pencil` also exposes `data-tip="195 186"`, and its graphite shape is `#pencil-tip`. This makes it possible to synchronize the tip with a revealed annotation stroke. Feet finish around `y=240`; the drawing fits within the 260-unit square. Move the whole SVG for the walk path, then animate the feet locally. Move the body, head, notebook, pencil, and wing together for a walking bob; animating the torso alone would separate the neck and notebook. A wrapper group may be added around those five groups when integrating the rig.

Use restrained motion: two short steps, a pause, a glance at a parcel, a glance at the notebook. The eye is the only deliberately tiny detail. Keep the notebook against the chest during walking. Reduced-motion mode should retain a complete static pose.

## Review

Rendered in Chromium at 150px and 300px and inspected at both sizes. The long bill and pouch, held notebook, and separate feet remain clear at 150px. The pencil reads as a small clipped tool; its graphite tip is a secondary detail. A second pass removed an unnecessary pouch line and added the separate pencil. No clipping was visible at either size.

An independent internal critique confirmed the silhouette and departure from the earlier origami direction. It also identified the shared upper-body motion requirement documented above. This is a static character asset; its eventual walk and drawing behavior still need to be tested in the parent scene.
