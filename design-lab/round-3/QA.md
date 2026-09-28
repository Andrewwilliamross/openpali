# Field Notes review

Reviewed September 27, 2026 UTC against the local built candidate.

## Visual review and revisions

Three parallel reviews covered the character, geographic sources, and composition/motion. The finished scene uses rounded SVG linework, a 61-parcel close-up, and a flat plan/elevation inset. The earlier paper-atlas page remains archived.

Browser review found and corrected a clipped tablet layout, overly faint mobile lines, an abrupt final foot landing, direction changes without anticipation, and an elevation incorrectly labeled as a section. Mobile now uses a dedicated viewBox, stronger parcel strokes, larger street names, and a readable motion control. Turns include a planted anticipation beat; foot transforms settle into rest.

The pencil tip and ink endpoint were sampled at 12.1, 14, and 15.8 seconds. Their screen positions agreed within 0.004px. Both are driven by the same SVG path position. The map paths stay fixed.

## Verified

- Python scene composition, Python compilation, JavaScript syntax, and the site build succeed.
- The deployment contains 10 allowlisted source files plus `.nojekyll`. Raw geometry, original sources, the design lab, and export tools are excluded.
- Layout reviewed at 320, 390, 768, 900, 1024, and 1440px after the final crop repair: no horizontal overflow; the bird stays inside the page. The earlier pass also covered 760 and 1800px.
- Pause freezes the shared clock. Resume advances from that time. Scrolling out and back preserves a manual pause.
- When the scene is offscreen, the clock stays fixed; it resumes when the scene re-enters view. The document-visibility handler uses the same suspension path.
- Reduced motion starts still. Explicit **Play once** runs a single cycle and returns to the still with **Play once** restored.
- Native field notes open exclusively. Source disclosure and the GitHub link remain ordinary HTML.
- With JavaScript disabled, the inline SVG and GitHub link load, the inactive motion control stays hidden, and there are no failed asset requests.
- Local screenshots and a full-loop recording were visually inspected. One non-blocking preload warning appeared during rapid automated reloads; the custom fonts loaded and no page JavaScript errors were observed in the final candidate.

## Review files

Local screenshots, animation GIF, and MP4 are in `output/design-round-3/` (not committed). The live review is `/dist/site/` after running the documented build. The implementation is the source of truth for timing; the art-direction document records the proposed storyboard.

PR #12 contains the candidate. A production deployment and manual GitHub social-preview upload are separate release steps.
