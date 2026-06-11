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

## Phase 3.5 — Volumetric Surface Closure & Projective Texturing

**Densification** (`surfels.sample_faces_stratified`): the LARIAC shells are no
longer sampled at mesh vertices (~0.5× surface coverage — visibly hollow) but
**stratified-barycentrically across every triangle face**: jittered-grid (r₁,r₂)
→ the area-preserving warp u=1−√r₁, v=r₂√r₁ → ~1.77× disk coverage at 0.75 m
spacing. Surfels carry the face normal (quat aligning ẑ→n), s_z=0.001 m
structural flatness, barycentric LARIAC colours, and an APN-stable RNG seed
(int(apn) — `hash()` is process-salted and would break nightly idempotency).
Result: **10.0 M surfels / 4,976 parcels** (universe 5,877 intact, 717 lots
have no LARIAC building data).

**Projective texturing** (`texturing.ts` + shader): per drawn node ≤400 m, the
Esri Wayback **pre-fire** orthophoto tiles covering its footprint are composed
(mercator-correct, async createImageBitmap) into one 256px texture; the
fragment shader projects each surfel's ENU position into it. The **anti-smear
mask** w_p = smoothstep(clamp(|n·ẑ|,0,1)) cross-fades photo→score-tint as faces
go vertical — roofs read as photography, walls stay clean data colour. Pre-fire
imagery on pre-fire hulls is deliberate (post-fire flights show rubble).
Texture residency is LRU-capped (112 MB) and tied to node eviction.

**Perf accounting fix**: GPU residency now counts slot *capacity*, not payload
bytes — pool peak dropped 1,264 → 496 slots (566 → 222 MB GPU) under the same
144 MB cap. Verified: 32 py + 17 ts tests, GL error 0 across pitch-85 sweeps,
photo roofs + tinted walls confirmed in-browser top-down and at street level.

## Phase 4 — Performance Profiling & Optimization

Root-caused and fixed the runaway-CPU / flicker / floating-geometry symptoms:

- **Startup cascade flood** (the fan): the zoom-out fallback recursed into
  *unloaded* subtrees, requesting the entire 2,375-node tree (326 MB + ~10 M
  main-thread sort ops) on first paint. Fallback now descends only where
  `residentDesc > 0`; loading is purely SSE-paced. Cold-start fetches: 2,375 → ~200.
- **Eviction thrash** ("everything in between states"): single 448 KB slots made
  GPU cost ≈ 3× payload, starving the cap into evict→reload→re-fade loops.
  BufferPool now has size classes (64/192/448 KB) + 120-frame hysteresis on
  node AND texture eviction. Settled state: zero evictions, zero re-fades.
- **Texture flicker**: same thrash through `texMan.evict` + per-frame
  re-compose; killed by the above + distance gating (≤2.5 km) on acquisition.
- **Floating sky blobs**: the terrain clamp applied a centre-sampled offset to
  multi-km internal nodes (centre-on-ridge hoisted coastal content hundreds of
  metres). Clamp is now size-gated (≤600 m); large nodes render at their
  already-correct absolute AMSL.
- **Repaint storms**: DEM probes throttled (15-frame cadence, repaint only on
  >0.25 m change); re-sort budget 1 → 4 nodes/frame so the post-move backlog
  drains in ~⅓ s instead of keeping the loop warm for hundreds of frames.
  Verified: **0 renders / 5 s at idle, pitch 85** (was a continuous ~25 fps loop).
- **Ground layer**: current-conditions Esri Wayback **2026-05-28** imagery as a
  native terrain-draped raster with a Map/Sat toggle (default Sat in 3D).
- **§III.1 audit**: antiparallel/near-antiparallel quaternion paths proven NaN-free
  (exact 180° fallback; overhang test); the GeoParquet tier now hard-rejects
  non-finite batches at the schema boundary.
- **§II audit**: no indexing discrepancy — 1,634/1,775 LADBS APNs join the
  5,877-parcel universe; the 141 others are permits on non-destroyed (Major/
  Minor) lots, correctly out of scope; 19 upstream rows have unparseable APNs.
- **§IV evaluation**: Open3D/trimesh rejected (registration + sampling already
  vectorised numpy/scipy; no mesh repair needed; ~700 MB dep). CuPy rejected
  (nightly drain is network-bound, 95 s warm). Frustum culling + ring-buffer
  recycling already present; tightened as above.

### Phase 4.1 — base-map flicker + true current-conditions ground

- **Flicker root cause**: the splat layer mutated GL state (blendFunc, depth
  mask, texture/program/VAO bindings) with raw calls; MapLibre v5's `Context`
  CACHES that state and skips "redundant" sets, so its next terrain-drape pass
  (which carries the ground imagery) intermittently ran with our state — the
  constant base-map flicker. render() now snapshots and exactly restores every
  mutated value, keeping cache == hardware.
- **Ground imagery**: Wayback "release dates" are publish dates, not capture
  dates — the world mosaic over the Palisades still shows pre-fire structures.
  Replaced with the **LA County LARIAC7 Post-Fire Ortho (flown October 2025)**,
  a public WMTS discovered inside the county's own Road-to-Recovery 3D scene
  (svc.pictometry.com, GoogleMapsCompatible, live to z21 ≈ 7 cm/px), bounded to
  its flight footprint with Esri World Imagery as the out-of-coverage fallback.
  The ground now shows cleared pads and early reconstruction — the truest
  publicly-served picture of June-2026 conditions.
