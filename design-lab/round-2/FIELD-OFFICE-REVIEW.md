# Field office · independent review

September 26, 2026. Internal product, design, and browser review of the implemented [website](../../site/index.html), [README](../../README.md), and [brand family](../../Docs/Brand/README.md). This is not resident research or external community feedback.

## Recommendation

Use the coastal atlas and working pelican as the primary identity. The page now presents a place and an activity: opening a record and following its context. The source, software, and correction illustrations extend that activity across the repository. This is a meaningful improvement over changing the material of a large P.

The headline has personality, while “Public evidence for the Palisades rebuild” immediately explains the project. The single GitHub action remains obvious. Open field notes connect the illustration to actual product principles without pretending the hero is a working map.

## What works, and what still needs judgment

- **Specific subject:** coastal paper terrain, tracing sheets, a source note, and the bird's action give the identity a recognizable scene. The pelican participates instead of replacing the monogram as a solitary object.
- **Consistent family:** the three role illustrations preserve the character, materials, palette, and source-related activity. They survive as small README cards. The wordmark, favicon, ASCII companion, and sticker give different formats appropriate assets.
- **Honest context:** the coast is visibly labeled illustrative. There are no property claims, recovery scores, damage scenes, or fabricated dates in the art. The correction note now specifies accepted corrections, and the date note explains distinct meanings.
- **Remaining creative limit:** the coast is an imagined landscape. It gives a local atmosphere, not verified Palisades geography. Keep the illustration label; don't promote the render into a geographic demonstration.
- **Remaining interaction limit:** notes reveal text and add a scene annotation. The paper and bird do not physically unfold or move through a new action. This is a light, understandable landing-page interaction. A future animated paper scene would require additional authored assets and testing.
- **Small labels:** note numbers, eyebrow copy, and artwork annotations are deliberately small. Their essential meaning is repeated in readable text. They should not acquire unique instructions or factual content later.

## Issues found and corrected

| Finding | Final result |
| --- | --- |
| Hiding the description's line break joined “for” and “the” on mobile. | A literal space preserves the sentence when the break is hidden. |
| The atlas bleed produced 5–6 px of horizontal overflow at 768 and 1024 px. | Revised positioning and the tablet stack remove overflow in the checked widths. |
| Very tight headline tracking joined letters and weakened word separation. | Tracking was loosened and the revised headline inspected on mobile. |
| The rotated caption crossed the illustration at narrow widths. | A shorter caption and explicit illustration label occupy the white margin. |
| The new caption wrapper inherited the arrow's font size and rotation. | The arrow style is restricted to its own span. |
| A keyboard focus outline crossed the first line of an open note. | Eight pixels of top padding separate the paragraph from the outline. |
| Long README card paragraphs became narrow columns on mobile. | Cards now contain the role and direct link; explanation sits below at full width. |
| Full-size role PNGs were oversized for README cards. | Display images are 640 × 427; three cards total roughly 410 KiB. Original sources are retained separately. |

## Final browser checks

Reviewed the served build at `http://127.0.0.1:4173/dist/site/` in Chromium through Playwright. Final checks used the updated page after the fixes above.

| Viewport width | Document width | GitHub action bottom edge |
| --- | --- | --- |
| 320 px | 320 px | 404 px |
| 390 px | 390 px | 389 px |
| 768 px | 768 px | 445 px |
| 1024 px | 1024 px | 546 px |
| 1440 px | 1440 px | 606 px |

The purpose and action remain in the first viewport at each width. All artwork loaded. The final 390 × 844 view was inspected with an open note and visible keyboard focus.

- Exactly one outbound link, to `https://github.com/Andrewwilliamross/openpali`.
- Keyboard Space opens note 02 and closes note 01; the scene annotation changes to the matching date note.
- With reduced motion, the scene transform is `none`; the information remains available.
- With JavaScript disabled, the hero, GitHub link, and native expandable notes still work.
- No page JavaScript errors were observed during the final pass.
- Cobalt, ink, and muted text on white have calculated contrast ratios of 5.47:1, 13.83:1, and 5.91:1 respectively. This is a palette check, not a full accessibility certification.
- The README's shell examples and licensing notice were checked against the preceding committed version and remain unchanged. Internal README section links resolve.
- Local links in the README, brand index, field-office guide, and this review resolve, including the final provenance record and ASCII companion.

The README layout was also inspected in a local Markdown preview with GitHub-like table sizing at desktop and 390 px. That is a layout approximation, not a claim to have verified the unpublished README on GitHub.

## Scope and remaining checks

This pass covers Chromium, the specific responsive widths, keyboard notes, static fallback, reduced motion, visual layout, copy, and repository links. It does not establish Safari/Firefox behavior, screen-reader output, physical mobile performance, or full WCAG conformance. The delivered images are generated illustrations; editable composition files do not make them geographic data or wholly vector art.

Keep the [licensing notice](../../README.md#license-and-data-rights) intact until the owner selects terms. Preserve source prompts, master images, font licenses, and export instructions with future artwork changes. Review the actual published README and website after deployment because hosting paths and GitHub rendering can differ from local previews.
