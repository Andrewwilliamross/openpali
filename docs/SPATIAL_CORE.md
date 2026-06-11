# Phase 2 — 4D Spatial Twin Core

Phase 1 answered *"how far along is the rebuild, lot by lot?"* with permit
records. Phase 2 gives every lot a **spatial memory**: a continuously
extensible 4D dataset (3D geometry × time) anchored to the same canonical APN
keys, built from LARIAC's authoritative 3D building model and designed to
absorb crowdsourced captures and 3D Gaussian Splatting reconstructions as the
rebuild progresses.

```
pipeline/core/spatial/
  geodesy.py        WGS84 ⇄ ECEF ⇄ ENU exact transforms; EPSG:2229 (CA SP-V) → WGS84
  schema.py         the unified state vector + partitioned GeoParquet store
  scene_client.py   LARIAC 3D extraction (I3S SceneServer, no Draco needed)
  registration.py   SOR → Mahalanobis → RANSAC coarse → ICP fine (full math)
  splat_tiler.py    3DGS octree LOD → 3D Tiles 1.1 + streamable .splat tiles
  runner.py         idempotent nightly job over the full 5,877-parcel universe
```

## The state vector

Every spatial primitive — a LARIAC mesh vertex, a registered crowdsourced
point, a trained Gaussian splat — is one row:

```
x = [ X_ecef  Y_ecef  Z_ecef   absolute position (m)
      T_epoch                  acquisition time (unix s)
      S(3)  R(4)  α            Gaussian scale / rotation quat / opacity
      Ψ(K×3)                   spherical-harmonics colour coefficients
      APN ]                    canonical 10-digit parcel key
```

Raw points are degenerate Gaussians (ε-scale, identity rotation, DC-only Ψ) —
one schema across modalities. Storage is a **hive-partitioned Parquet dataset**
keyed by Uber H3 resolution-8 cells (with a per-row res-12 index column), plus
a **GeoParquet 1.1 asset index** (`assets.parquet`) that QGIS/GDAL/DuckDB read
directly. No per-parcel flat JSON anywhere.

## LARIAC ingestion (the spatial prior)

The `Palisades_3D_Buildings` SceneServer (LA County eGIS, I3S 1.10) carries
APN/AIN/HEIGHT/DINS attributes natively and exposes an **uncompressed**
geometry buffer — vertices decode with `struct` + numpy, no Draco. The client
walks nodepages → decodes triangle-soup vertices (Float32 offsets about each
node's OBB centre; x/y degrees, z metres EGM96 → ellipsoidal via local geoid
offset) → slices per-feature via faceRanges → joins index-aligned APN
attribute buffers. A one-time APN→node index (disk-cached, store-version-aware)
makes per-parcel extraction O(nodes containing that parcel).

Fallback for unmodelled lots: LARIAC footprint polygons + HEIGHT/ELEV
(`WildFire_Palisades_DINS_Plus_BuildingOutlines_VIEW`) extruded into wall/roof
point priors.

## Registration (crowdsourced → absolute space)

`register_capture(capture, prior)` runs the full chain in local-ENU metres:

1. **SOR** — k-NN distance gate (structure-preserving denoise)
2. **Mahalanobis prefilter** — χ²₀.₉₉₉(3) gate against the capture's own
   distribution (kills GPS multipath / telemetry drift)
3. **RANSAC coarse** — voxel downsample, 5-D local-geometry descriptors,
   congruence-checked 3-point hypotheses, Kabsch solve, NN-inlier scoring
4. **ICP fine** — trimmed point-to-point with per-iteration **Mahalanobis
   residual gating** (anisotropic outlier rejection), SVD/Kabsch updates

Acceptance gate for the canonical store: converged, RMSE < 0.75 m, >50%
inliers. Tested against ground truth: recovers a 17° + 1.5°-tilt, 6 m offset
under 5 cm noise and 8% gross outliers to <2° / <0.35 m — and the same on real
LARIAC geometry in the integration suite.

## 3DGS LOD tiling

`tile_batch` compiles a Gaussian batch into a 3D Tiles 1.1 octree pyramid:
leaf nodes carry raw splats; internal nodes carry **opacity-weighted
centroid-clustered** representatives whose merged covariance is the cluster's
true second moment (Σ* = Σwᵢ(Σᵢ + dᵢdᵢᵀ), eigen-decomposed back to
scale+quaternion), with SH bands above DC pruned. Payloads are the 32-byte
web `.splat` format; the tileset root carries the exact ENU→ECEF rigid
transform. Verified invariants: leaves preserve every input primitive,
geometric error shrinks monotonically down-tree, internal nodes respect the
grid³ budget.

## Nightly job

`uv run run_spatial.py [--limit N] [--apn ...]`

- Evaluates against the **complete 5,877-parcel universe** every run; lots with
  no spatial data get explicit `static_baseline` rows (never dropped).
- Idempotent: same-night re-runs overwrite, the asset index keeps the newest
  row per (APN, kind).
- Fail-safe: per-source and per-parcel exception isolation; failures preserve
  the last valid asset (`stale_cached`) and land in `store/meta.json` as
  flagged anomalies.

## Verification

`uv run pytest tests/test_spatial.py tests/test_spatial_integration.py`
— 16 tests: sub-mm geodesy round-trips, Parquet/GeoParquet round-trips +
idempotency, SOR/Mahalanobis behaviour, Kabsch exactness, RANSAC basin
capture, ICP convergence, ground-truth SE(3) recovery (synthetic + real LARIAC
geometry), octree LOD invariants, quaternion algebra round-trips.

## Phase 3 — 3D Spatial Navigator (web/src/components/spatial/)

The 2D tracker becomes an Apple-Maps-Flyover-style navigator: MapLibre terrain
(AWS terrarium DEM, 60–85° pitch, hillshade + sky atmosphere) with a custom
**shared-context WebGL2 splat layer** streaming the Phase 2 LOD pyramid.

- `SplatRenderLayer.ts` — CustomLayerInterface (`renderingMode: '3d'`): SSE-driven
  octree traversal with REPLACE refinement + parent↔child cross-fade, GPU ring
  BufferPool (448 KB slots, LRU eviction), per-node depth sorting (16-bit
  counting sort, ~5.7° re-sort threshold), terrain z-clamping on per-node
  **content min-z** (tileset `extras.contentMinZ`) with a DEM-streaming guard,
  and depth-test-on/depth-write-off blending against MapLibre's terrain depth.
- `shaders.ts` — EWA splatting with the Jacobian derived analytically from the
  final ENU→clip matrix (no focal-length/axis-convention assumptions), 2×2
  eigen quad construction at √8σ, isotropic-splat NaN guard, 250 ms temporal
  fade, premultiplied-alpha output.
- `spatial_intersector.ts` — 3D picking: screen ray (inverse f64 matrix) vs
  per-APN bounding prisms from `picking.json`, **terrain-shift-aware** (applies
  the renderer's clamp formula per parcel at pick time).
- `ParcelDetailCard.tsx` — floating glass card: score with stage-matched glow,
  milestone timeline, grouped pre-fire metadata, official-record links.
- Buildings are tinted by **rebuild score** (the map ramp, luminance-modulated
  by LARIAC vertex colours) — the pre-fire hull of every home, coloured by how
  far its rebuild has come.

Verified end-to-end in-browser: terrain + splats + GL error 0, SSE streaming,
3D click → APN → card. Hardened by a 10-agent adversarial review (confirmed
findings fixed: cube-bottom clamp anchor, DEM-race sea-level clamp, VAO/
ARRAY_BUFFER state misconception, oversize-buffer leak, REPLACE-fade pop,
zoom-out holes, generation-guarded async loads, retryable fetch failures).
