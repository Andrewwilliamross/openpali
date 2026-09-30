# Signal / white and blue

This revision follows the selected Signal screenshot: a sparse landing page with a large sans-serif headline, one GitHub action, and scattered square artwork. White is the main background; cobalt supplies the headline, action, and square accents. The squares never form a letter.

## Platform copy

**Understand the rebuild.**

OpenPali brings siloed public records, geospatial data, and imagery into one platform for analyzing the Palisades rebuild.

The README expands this into source integration, geographic exploration, and analysis. The supported examples are agency records and permits, optional imagery, LiDAR-derived terrain, milestone prevalence, permit flow and backlog, and time to issuance. Analytics run through the platform services and published release APIs/CSV; the bundled frontend snapshot supports local map exploration.

The [source registry](../../pipeline/openpali/adapters/registry.py), [spatial pipeline](../../pipeline/openpali/spatial/), and [metric catalog](../../pipeline/openpali/metrics/catalog.py) support this framing. It makes no claim of complete live coverage, production automated imagery change detection, or approved prediction models.

## Implementation

- Original deterministic SVG field: 646 squares on a 25×29 grid, varied size and opacity.
- Fine-pointer emphasis changes nearby square size and opacity around fixed centers. There is no autonomous animation or glyph state.
- Touch and reduced motion stay static. No JavaScript is needed for the complete composition or GitHub link.
- Shared DM Sans font and license; no external font or rendering dependency.
- Matching banner, social card, avatar, favicon, wordmark, and ASCII companion in [`assets/brand/signal/`](../../assets/brand/signal/).

Build with `python3 scripts/build-site.py`. When serving the repository root, review `/dist/site/`. The previous pelican page is archived at [`../round-3/field-notes/`](../round-3/field-notes/).

## Verification

- Browser checks at 320, 390, 700, 768, 1024, 1440 and 1800px: white background, heading fits, no horizontal overflow, primary action visible in the first 900px viewport.
- Pointer review: 75 nearby tiles responded; every square center stayed fixed within 0.002 SVG units. Returning over the text restored every size and opacity exactly.
- Reduced motion remains static. Keyboard Tab reaches the GitHub action first.
- No JavaScript: 646 squares, correct GitHub destination, no layout controls, and no failed asset requests.
- Python compilation, JavaScript syntax, eight-file site build, and whitespace checks pass.
- README claims were checked against the source adapter registry, spatial pipeline, and analytics API/catalog. Setup instructions and license text were preserved.

Screenshots and deliverables are in local `output/design-round-4/`.
