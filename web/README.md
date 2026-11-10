# OpenPali map

React + TypeScript + Vite + MapLibre, with a custom WebGL2 mesh renderer for the
3D structures.

From the repository root:

```sh
npm --prefix web ci --cache .npm-cache
make evidence-build
make evidence-api  # terminal 1, localhost:8000
make evidence-web  # terminal 2, localhost:5173
```

The source acquisition cache must exist before `evidence-build`; build errors
identify missing or altered inputs. It never silently substitutes fixtures.
The map reads one evidence release when it loads. Reload to adopt a new one.

The interface is the map plus two controls: an address / APN search and a
neighborhood picker. Each flies the camera to its view.

- **Ground:** EagleView 2026 county mosaic over Esri World Imagery, draped on
  terrain: USGS 2025 post-fire lidar (2 m tiles) where the scene build baked
  it, Mapzen terrain tiles elsewhere.
- **Structures:** the county's 2023 building model as indexed triangle meshes
  (`src/components/scene/`), 12,595 structures in 91 batches, about 25 MB.
  Structures the county inspected as destroyed are drawn as outlined,
  translucent shells in their lot's score colour, so the cleared lot in the
  2026 imagery stays visible; standing structures are solid with the aerial
  photo on their roofs. This is what stood before the fire, not current
  construction. County terms label the model non-authoritative and restrict
  its use.
- **Shading:** lots and destroyed structures share one 0–100 rebuild score:
  the position of the parcel's highest agency-reported recovery milestone
  (`stages` in `src/lib/api.ts`, ramp in `src/lib/colors.ts`). Only parcels the
  agency fire assessment records as destroyed are scored. A structure's colour
  is one texel in a lookup texture, updated without touching geometry.

The scene is a generated artifact, not part of this directory:

```sh
make scene-plan    # what a build would fetch that is not cached
make scene-build   # fetch (cached in data/raw/scene), compile, register, bake terrain
make scene-verify  # hashes, id integrity, registration, terrain
```

The dev server serves the scene `data/out/scene/current.json` names at
`/scene/`; in a container, mount it with `infra/compose.scene.yaml`. Without a
scene the map still shows terrain, imagery and scored lots.

The evidence API still serves property records, claims and acquisition tasks;
this interface does not present them.

## Checks

```sh
npm --prefix web test -- --run
npm --prefix web run lint
npm --prefix web run build
sh scripts/check-fast
```

## API contract

FastAPI owns `contracts/openapi.json`. After an API change, export it from the
repository root with `pipeline/.venv/bin/python -m openpali.api.app export-openapi`
and update `web/src/lib/api.ts` as needed. The fast gate checks schema drift.

## Project identity

The current [Signal brand kit](../Docs/Brand/README.md) supplies the OpenPali
mark, favicon and local DM Sans font. See the
[contributor guide](../CONTRIBUTING.md) for the shared workflow.
