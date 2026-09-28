# OpenPali — design review

> Archived first exploration. See [Round 2](round-2/README.md) for the current Field Office direction and live gallery.

**Provisional direction:** Assembly's participatory hero, Fieldnotes' editorial clarity, and Signal's blue treatment for social and launch materials. This is a recommendation for the project owner to choose or change; the existing production site remains current.

The exercise tested different media and interactions. White, blue, and transparency are shared constraints; layout, material, motion, and reading order are the variables.

## Six alternatives

| Direction | What the experiment proves | Strongest use | Main tradeoff | Engineering cost |
| --- | --- | --- | --- | --- |
| [01 · Fieldnotes](concepts/01-fieldnotes/index.html) | Oversized type, thin rules, asymmetric columns, and an optional margin annotation can carry the identity without imagery. | A credible civic introduction and readable project documentation. | It explains the purpose better than the actual map experience. Tiny folios must remain decorative. | **Low:** native layout and one local toggle. Typeface changes need optical review. |
| [02 · Ledger](concepts/02-ledger/index.html) | Transparent sheets, CSS perspective, layer selection, and a depth slider make source → observation → release tangible. | An explanatory section about evidence and traceability. | Card details become small on mobile; the illustrative label must remain conspicuous. | **Moderate:** stacking contexts, tab semantics, responsive geometry, and blur fallbacks. |
| [03 · Assembly](concepts/03-assembly/index.html) | A live, lit P made of instanced cubes can be pulled apart and reassembled. The visitor has something meaningful to do. | The principal website hero: playful, recognizable, connected to contribution. | An abstract mark needs the plain project-purpose sentence beside it. | **Moderate:** Three.js, GPU rendering, resize/visibility handling, SVG fallback, and device testing. |
| [04 · Signal](concepts/04-signal/index.html) | Scale and a responsive field of squares create a strong blue poster; a toggle gathers or scatters the mark. | Launch cards, social headers, announcement pages, and a deliberate high-energy variant. | A slogan and a field do not explain the product alone. Preserve readable descriptive copy. | **Moderate:** live instanced WebGL field; a static export has a much smaller operating cost. |
| [05 · Material](concepts/05-material/index.html) | An original Blender sculpture can overlap real HTML type, using a transparent render and subtle image parallax. | An identity object for a release cover, event slide, or calmer website hero. | Attractive optical depth does not explain evidence flow. Refraction and lighting are baked into the image. | **Higher authoring / low browser cost:** editable Blender scene, render/export cycle, image optimization. |
| [06 · Aperture](concepts/06-aperture/index.html) | A generated optical still and a split glass button express transparency with very little UI. | A material reference or quiet campaign composition. | The object is less distinctive to OpenPali. A mobile crop and background seam needed a second composition pass. | **Low browser / image-dependent authoring:** HTML/CSS and one still; future revisions require new image work. |

The first four are code-native compositions. Material is a reproducible offline 3D render. Aperture is an ImageGen still. Their production and interaction costs are different even when a screenshot makes them look equally dimensional.

## Components worth carrying forward

The [button lab](components/index.html) compares eight actual GitHub links: solid, outline, glass, offset, ticket, editorial, assembly, and portal. Its state switch previews rest, hover, focus, and press treatments.

- **Solid or assembly:** the clearest primary invitation for the proposed hero.
- **Editorial:** useful for documentation and restrained secondary surfaces.
- **Glass or portal:** coherent with a material-led composition, provided text and focus remain opaque and legible.
- **Ticket and offset:** expressive alternatives; keep them as deliberate choices rather than mixing all eight styles.

The [component lab](components/evidence.html) adds a source card, native disclosures, keyboard-operated evidence tabs, and a contributor invitation. These demonstrate behavior with illustrative text. They are not wired to the production API or approved replacements for the map's components.

## Internal critique forum

These are actual observations exchanged by the agents building and reviewing this set, plus author critiques. They are internal design judgments, not external community feedback or user research.

| Perspective | Observation | Result or recommendation |
| --- | --- | --- |
| Editorial/UI author reviewing Assembly and Signal | Assembly's coherent cube form and shadow make play purposeful. Signal has the strongest poster impact. Both originally hid the civic purpose behind general slogans or a small footer. | Both authors added a direct Palisades-purpose sentence and loosened headline tracking in their second pass. Signal also regularized the P tiles and adjusted mobile clearance. |
| WebGL author reviewing Fieldnotes, Ledger, and Material | Fieldnotes communicates civic purpose most clearly. Ledger gives the evidence relationship a concrete interaction, but miniature tilted cards may resemble a shipped product screenshot. | Preserve Fieldnotes' hierarchy and Ledger's illustrative label. Choose Assembly or Material as the main visual, and reserve Signal for launch moments; avoid combining every effect. |
| Fieldnotes self-review | Initial kerning was too tight, and removing mobile line breaks joined words. | Loosened the wordmark, preserved spaces, and adjusted mobile spacing. |
| Ledger self-review | Rear sheets competed with the active one; the initial ordering and wrapped tab weakened the metaphor. | Dimmed rear contents, corrected initial layer order, kept tab labels on one line, added keyboard-focusable active panels, and added a flat state at zero spacing. |
| Material author reviewing the other studies | Preferred Fieldnotes plus the physical Material object. Flagged inconsistent mark silhouettes, tiny instruction labels, Ledger’s small mobile text/numeric spread value, and Aperture’s mobile crop/background seam. | Treat Material as a genuine alternative to Assembly. Ledger now uses qualitative spacing labels and larger, less tilted mobile details. Aperture’s crop/seam and the glass specimen’s caption overlap received parent revisions. Unify the final mark and distinguish decorative labels from instructions. |
| Material self-review | Real optical depth and a reusable object are valuable; the image is heavier than vectors and its refraction cannot react to new backgrounds. | Keep the editable scene, optimize delivered images, and judge whether the detached square reads as an invitation. |
| Aperture author | The glass directly answers the transparency brief, but could belong to many premium software brands. | Keep OpenPali's identity explicit. The parent revised the headline to “A clearer picture. Built in public.” and the footer to “PUBLIC CODE”; the mobile object moved inward and gained an edge fade. |

## A coherent synthesis

The reviewers agree on Fieldnotes’ clarity and Signal’s social role. The hero choice is still open: the material reviewer preferred the rendered object; the WebGL reviewer supported Assembly or Material. The recommendation below favors Assembly because its interaction directly answers the request for play.

1. **Use Assembly for the hero.** Keep one obvious GitHub action, the simple purpose sentence, the assembly slider, and a static/SVG fallback. The interaction should settle when the visitor stops using it.
2. **Borrow Fieldnotes' discipline.** Use deliberate margins, rules, readable type, and short copy. Carry that treatment through the README, contribution guide, and release notes.
3. **Apply Signal to social.** Export a consistent blue poster system for landscape and square formats. Keep the P and typography recognizable at thumbnail size.
4. **Use Ledger selectively.** Its evidence stack belongs in an explanatory or methods surface where the extra interaction helps understanding.
5. **Keep Material and Aperture as distinct alternatives.** Material is the stronger route if a rendered object replaces live WebGL. Aperture is a useful optical reference, with wording and identity specificity still to resolve.

This proposes one primary behavior and a few related treatments, not a collage of all six heroes.

## Implementation checklist

### Completed in this exploration

- [x] Built six separate landing concepts and an interactive comparison gallery.
- [x] Completed and rendered the 18-slide deck at `output/design-review/OpenPali-Design-Review-Edition-01.pptx`; final package, geometry, font and import checks passed. Each final slide received visual review.
- [x] Built eight button specimens and four evidence/contribution component specimens.
- [x] Explored CSS layout, CSS 3D, live Three.js scenes, an original Blender render, and a generated material still.
- [x] Preserved editable code and material sources; recorded runtime dependencies and image provenance.
- [x] Added reduced-motion handling, visible focus, responsive layouts, and native controls across the relevant studies.
- [x] Reviewed concept screenshots and recorded concrete peer/self-critique; revised type, copy, layers, and controls.

### Before replacing production

- [ ] Project owner chooses a direction or approves the proposed synthesis.

- [ ] Reconcile final project wording, naming, logo variants, and license status across every selected asset.
- [ ] Establish one shared mark silhouette, type scale, spacing system, button treatment, and responsive composition. Resolve the open-ring versus pixel-P variations.
- [ ] Review tiny labels, mobile sheet legibility, qualitative depth-control wording, image crop/seams, and decorative layers behind component captions.
- [ ] Finish cross-browser, keyboard, enlarged-text, forced-colors, reduced-motion, and WebGL-failure checks on the chosen implementation.
- [ ] Measure download size and runtime cost on representative mobile hardware; optimize the chosen images or WebGL bundle.
- [ ] Adapt the selected system to README, social cards, and the one-button website; keep prototype data labels out of factual claims.
- [ ] Review the final diff, publish deliberately, and verify the live destination.

## Source notes

The presentation references remain [Omarchy, Prime Agent, and GeoLibre](../Docs/Brand/REFERENCES.md). They informed consistency, invitation, and project storytelling; their artwork was not reused.

For the implemented techniques, see the official [Three.js documentation](https://threejs.org/docs/), [Blender Python API](https://docs.blender.org/api/current/), and [Blender rendering overview](https://docs.blender.org/manual/en/5.0/render/introduction.html). Exact versions, local assets, and reproduction paths are listed in [README.md](README.md).
