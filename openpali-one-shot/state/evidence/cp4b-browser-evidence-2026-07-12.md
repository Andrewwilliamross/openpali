# CP4B browser evidence: renderer draw calls, tile requests, picking, labels

Job: `e2e-browser` (image openpali-e2e:local, FROM digest-pinned
mcr.microsoft.com/playwright:v1.61.1-noble), run via
`python3 openpali-one-shot/scripts/docker_safe.py -f infra/compose.yaml up -d e2e-browser`
against the RUNNING web/api containers on the internal network; external tile
hosts reached only through the labeled egress proxy (E2E_PROXY, Chromium
--proxy-server with bypass for web/api).

## Result (2026-07-12, container exit 0)

    ✓ 1 e2e/spatial-usgs.spec.ts:46:5 › USGS post-fire surfels: tile
        requests, draw calls, picking, labels (1.3m)
    ✓ 2 e2e/spatial-usgs.spec.ts:122:5 › 2D journey stays usable and the
        post-fire hillshade is present (11.8s)
    2 passed (1.5m)

What the passing spec ACTUALLY asserted (web/e2e/spatial-usgs.spec.ts):
- release-qualified network requests over the wire:
  `/v1/releases/rel-*/spatial/usgs-surfel-aoi/sv-*/...` manifest + `.splat`
  payloads, plus `usgs-terrain-aoi` terrarium PNGs (post-fire hillshade);
- REAL instanced draw calls: `window.__usgsSplats.stats` cumulative frames >
  0, drawnNodes > 0, drawnSplats > 1000 after a deterministic jump into the
  frozen AOI;
- picking: a click at the AOI center ray-picks a parcel prism and opens the
  detail card, which shows the `Post-fire surface (2025-01-21)` provenance
  badge and a formatted APN;
- legend labels the source with its ACQUISITION (flight) date: "USGS
  post-fire lidar bare earth (flown 2025-01-21, preliminary)";
- 2D journey: leaving 3D keeps the evidence legend usable and the
  release-served `postfire-dem` raster-dem source present.

Headless disclosure: WebGL runs on SwiftShader/ANGLE inside the container;
the spec records the unmasked GL renderer in its annotations and this
evidence supports CORRECTNESS only — no GPU/performance claim (SPATIAL-002
performance work uses the separate renderer-bench job and records hardware
acceleration state explicitly).

Diagnosed on the way: `map.loaded()` polling never settles while custom
layers keep the render loop warm — the app now exposes a one-shot
`__mapReady` load signal; the mode toggle's accessible name is its
aria-label ("Toggle 3D view"), which overrides the visible text.
