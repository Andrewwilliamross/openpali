# Living Atlas

Serve the repository root, then open `/design-lab/round-2/atlas/`.

- Drag the atlas horizontally, or use the fold slider with a pointer or keyboard.
- Three different sheets explain event, observation, and publication dates.
- The coastline is original illustration, with no property or recovery data.
- [Critique and engineering notes](critique.md) describe the iterations, actual rendering approach, fallback boundary, and checks.
- [QA results](qa-results.json) record the browser verification.

The fallback SVG can be regenerated with `python3 design-lab/round-2/atlas/make_poster.py`. The live scene uses the existing local Three.js modules and the shared Field Office fonts.
