# OpenPali · the map

The public interface for exploring Palisades recovery evidence: a searchable
2D map, property timelines, source context, and optional 3D. Built with React,
TypeScript, Vite, MapLibre GL, and a WebGL2 renderer.

## Start here

Use Node.js 24 to match CI. From this directory:

```sh
npm ci
npm run dev
```

Open the URL Vite prints (normally `http://localhost:5173`). The repository
includes a static data bundle under `public/data/`, so you can work on the
map without starting the backend. This is a saved fallback, not a live feed.
External basemap tiles still need network access.

The development server proxies `/v1` and `/health` to the API at
`http://localhost:58000`. To use live releases, correction submission,
forecasts, source status, and release-selected post-fire spatial assets,
start the [local platform](../infra/README.md). Without it, the map displays
the bundled fallback and API-dependent features remain unavailable.

## Routes and code

| Route or directory | Purpose |
| --- | --- |
| `/map` | Main map; `/` redirects here |
| `/property/:apn` | Shareable property selection using a 10-digit APN |
| `/methods` | What the evidence, dates, statistics, and imagery mean |
| `/status` | Source and release status |
| `src/components/MapView.tsx` | MapLibre map and optional 3D loading |
| `src/components/spatial/` | Property card, forecasts, corrections, rendering, and tile handling |
| `src/lib/` | API-to-view mapping, coverage, formatting, and spatial source discovery |
| `src/api/generated/` | Generated API client; regenerate instead of hand-editing |
| `e2e/` | Playwright checks against the running platform |

The UI starts in 2D. The 3D renderer loads on request and requires WebGL2.
Post-fire spatial URLs are selected from a release manifest. Historical
imagery and models must retain their dates and rights labels.

`App.tsx` loads bundled geometry and details, then overlays API release
metadata and counts when available. Preserve the distinction between the
saved fallback and API data when changing this path.

## Everyday checks

```sh
npm test
npm run lint
npm run build
```

The build runs TypeScript checking before Vite. `npm run preview` serves the
production build for a local frontend check; Vite's development API proxy
does not apply to that preview server.

The repository-wide `../scripts/check-fast` runs the Python and web unit
suites, lint, type checks, and API drift checks. Playwright runs separately
against an initialized platform:

```sh
npx playwright test
```

Install the browser dependencies for your environment first, or use the
`e2e-browser` Compose job documented by the platform configuration.
`playwright.config.ts` defaults to `http://localhost:58080`; set
`E2E_BASE_URL` to use another local instance. Headless 3D checks use software
rendering, so their timings are not hardware GPU benchmarks.

## API contract

FastAPI owns the schema. After changing the API, run these commands from
the repository root with the Python environment and web dependencies installed:

```sh
pipeline/.venv/bin/openpali export-openapi > contracts/openapi.json
cd web
npx openapi-ts
npm run build
```

The generator reads `openapi-ts.config.ts` and writes `src/api/generated/`.
Commit the contract and client with the API change. `scripts/check-fast`
compares the exported schema with the committed contract.

## Working on the interface

Use evidence labels that say exactly what a source documents. Missing public
evidence is an explicit state, and scheduled inspections are not inspection
outcomes. Keep source links, release identity, fallback states, and property
correction paths visible.

Check keyboard access, narrow layouts, and reduced-motion behavior for UI
changes. See [CONTRIBUTING.md](../CONTRIBUTING.md) for the shared workflow.
