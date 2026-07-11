# openpali Research Audit

Prepared for Radu B. Rusu and Andrew Ross. Last updated 2026-06-11.

## Executive summary

openpali is already beyond a toy prototype. The repo contains a static civic data
pipeline, APN-keyed parcel artifacts, a GeoParquet spatial store, a 10M-splat
web-exported 3D layer, and a custom MapLibre/WebGL2 renderer. The current
artifacts report:

- 5,877 destroyed parcels in `web/public/data/summary.json`.
- 4,596 LADBS permit rows in `web/public/data/meta.json`.
- 10,016,113 score-tinted splats in `web/public/tiles/palisades/manifest.json`.
- 4,976 parcels visible in the splat picking index, leaving 901 destroyed
  parcels without rendered 3D splat coverage.
- 717 parcels marked `static_baseline` in `data/spatial/meta.json`.

The main gap is not ambition or rendering craft. The main gap is production
trust: provenance, repeatability, uncertainty, privacy, role-based access,
resident workflows, and a true continuous reconstruction loop. Today the system
is a strong public tracker plus a pre-fire/current-context 3D viewer. To become
community infrastructure, it needs auditable source lineage, parcel-level
confidence intervals, policy-sensitive modeling, secure resident document flows,
and a capture-to-reconstruction pipeline that can absorb drone, street, mobile,
contractor, and official imagery over time.

## Current strengths

- The project uses APN as a civic spine, which is exactly the right organizing
  key for parcels, permits, inspections, debris removal, imagery, contractor
  activity, and insurance claims.
- The data-source strategy is realistic: county debris parcels define the
  destroyed-parcel denominator; LADBS provides rich City-of-LA event timelines;
  Malibu and county-unincorporated feeds degrade to coarser status.
- The artifact contract is simple enough to host statically and audit by git
  history.
- The spatial side has real engineering depth: WGS84/ECEF/ENU geodesy,
  H3-partitioned Parquet, LARIAC I3S extraction, surfel densification, 3D Tiles
  style LOD, and WebGL2 streaming.
- Test health is good as of this audit: `uv run pytest` passes 35 Python tests;
  `npm test` passes 17 web tests; `npm run build` passes.

## Not production grade yet

1. **No formal source lineage or data contract layer.** The code records source
   health in `meta.json`, but it does not yet persist raw-response hashes,
   schema fingerprints, query parameters, row-level lineage, source-license
   terms, or transform versions beside every derived metric.

2. **The static JSON artifact model will strain under time-series analytics.**
   Git history is a clever bootstrap, but it is not enough for querying
   multi-run lag, survival models, source regressions, appeal history, and
   neighborhood comparisons. The spatial system already uses Parquet; the civic
   event model should join it.

3. **Predicted completion is too deterministic.** `score.py` uses conditional
   medians and humanized ranges. That is honest for v1, but production should
   expose calibrated uncertainty, censoring, jurisdiction effects, contractor
   availability, plan-check correction cycles, insurance delays, debris status,
   utility readiness, hillside/geology constraints, and policy regime changes.

4. **3D is still mostly a prior, not a real 4D reconstruction stream.** The
   current splat layer visualizes LARIAC-derived pre-fire shells tinted by
   rebuild status and draped over post-fire/current orthophoto context. It does
   not yet continuously ingest resident/drone/street captures, produce
   parcel-local learned 3DGS, track construction changes, or quantify geometry
   confidence by date.

5. **Splat coverage is incomplete.** The rendered splat manifest covers 4,976
   parcels; the civic denominator is 5,877 parcels. Baseline polygons preserve
   the denominator, but residents whose parcels lack 3D geometry will perceive a
   missing-home problem unless the UI explicitly explains coverage and offers a
   capture path.

6. **No resident-grade privacy/security model.** The public tracker is fine for
   public records, but insurance documents, contractor bids, photos from private
   property, utility account details, claim numbers, and neighborhood message
   threads need consent, access control, encryption, redaction, retention, and
   revocation.

7. **No adversarial governance for AI agents.** DoNotPay-style features can help
   residents, but high-stakes claims, taxes, citations, permitting, and
   contractor disputes require traceable citations, user confirmation, escalation
   to licensed professionals, and no unsupported legal or insurance advice.

8. **No operational alerting.** The pipeline catches some anomalies, but a real
   civic service needs scheduled runs, source SLA monitors, failed-join alerts,
   dashboard drift notices, schema-diff alerts, and public incident notes when
   upstream systems break.

9. **No feedback loop from residents.** The system shows official status, but it
   does not yet let residents correct a bad join, report a missing permit,
   submit evidence, flag a bad official record, or coordinate block-level needs.

10. **Performance budgets are not productized.** Web build passes, but the main
    JS bundle is 1.26 MB minified and the 3D tile payload is 326 MB. Mobile,
    metered connections, older devices, and disaster-displaced residents need
    explicit 2D-first/3D-on-demand budgets.

11. **No blueprint-conditioned geometry pipeline.** The audit recommends
    submitted-plan overlays, but LADBS/ePlanLA submittals are often flat PDF
    drawings or vector/raster sheets, not immediately usable 3D constraints.
    openpali needs a plan-to-geometry parser before architectural plans can
    safely anchor reconstruction.

12. **No generative hallucination control.** 3D diffusion priors, neural fields,
    and visual inpainting could help communicate blind spots, but without hard
    parcel, zoning, plan, height, and source constraints they risk inventing
    non-existent homes, rooflines, interiors, or progress milestones.

13. **No explicit sensor-fusion trust model.** LARIAC priors, resident mobile
    captures, contractor photos, aerial orthos, satellite imagery, plans,
    insurance estimates, and utility signals all have different time, accuracy,
    privacy, and legal semantics. Today the architecture does not define how to
    weight or decay conflicting realities.

## Hard scientific questions

These are the boundary-line questions that should be used in design reviews.
They are intentionally sharper than unit-test coverage: each one asks whether
the current architecture survives the place where geometric theory meets messy
public data, browser GPUs, uncalibrated mobile video, and censored civic
processes.

### 1. Zero-prior cold starts

Current state: `run_nightly` falls back to `extract_footprint_prior` when an APN
is absent from the LARIAC scene index, but the latest spatial manifest still
shows only 4,976 parcel splat records against a 5,877-parcel denominator. The
fallback also returns `mesh_vertices`, while the web export currently reads
`kind="splats"`, so a cold-start lot may be indexed but still visually absent
from the 3D stream.

Hard question: if a resident uploads an unstructured mobile video for one of the
901 non-rendered parcels, what anchors the first coordinate frame? Without a
forced geometric prior, such as an extruded LA GeoHub/LARIAC footprint, a parcel
centroid, known ground plane, and optional street/curb control points, SfM/SLAM
pose initialization is exposed to scale drift, yaw ambiguity, and catastrophic
pose divergence.

Pass bar:

- Every APN has a cold-start prior that is renderable, registerable, and
  explicitly labeled: LARIAC mesh, footprint extrusion, parcel polygon prism, or
  no geometry.
- `register_capture` rejects "no prior" captures unless enough external anchors
  exist: RTK/GNSS, survey control, AprilTag/ArUco markers, curb/road centerline
  alignment, or multi-view overlap with neighboring known parcels.
- The capture UI computes a pre-upload observability score: baseline/parallax,
  loop closure, texture richness, GPS dispersion, and prior availability.
- The registration report stores uncertainty, not just `accepted`: covariance of
  SE(3), inlier spatial distribution, minimum control-point count, and failure
  reason.

### 2. Measurable geometry from splats

Current state: surfel densification produces visually closed building shells,
but 3D Gaussians do not have native surface topology. A contractor or insurer
cannot safely measure area, wall plumbness, grading quantities, or roof
dimensions directly from alpha-blended splats.

Hard question: what is the explicit mesh extraction path? A naive Poisson
surface reconstruction over downsampled surfels can invent surfaces across
openings, smooth sharp construction edges, and produce non-physical topology.
The stronger path is a separate measurable-geometry product: fuse depth or
multi-view evidence into a TSDF/SDF volume, extract surfaces with Marching
Cubes, then compare that mesh against splat-rendered evidence and official
plans.

Pass bar:

- openpali maintains separate artifacts for "visual splats" and "measurable
  surfaces"; the UI never pretends the former is survey-grade.
- For resident/drone captures with depth or reliable MVS, fuse into
  parcel-local TSDF/voxel blocks, run Marching Cubes, then compute mesh quality
  metrics: hole ratio, watertightness, edge-length distribution, normal
  consistency, and reprojection residuals.
- For 3DGS-only scenes, evaluate surface-aligned approaches such as SuGaR or
  Gaussian-Mesh anchoring, but require independent metric validation before
  enabling exports for claims or contractor quantities.
- All measurements carry uncertainty bands and source labels.

Primary references: Curless and Levoy's volumetric range integration with
weighted signed-distance fusion, KinectFusion-style TSDF tracking/mapping,
SuGaR surface-aligned Gaussian splatting, and Dynamic Gaussians Mesh. Sources:
https://graphics.stanford.edu/papers/volrange/volrange.pdf,
https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/ismar2011.pdf,
https://arxiv.org/abs/2311.12775, https://arxiv.org/abs/2404.12379

### 3. Appearance mismatch in temporal reconstruction

Current state: the web renderer projects pre-fire orthophoto texture onto
pre-fire hulls and score-tints the result. That is coherent for visualization,
but it is not a training strategy for crowdsourced, multi-temporal 3DGS.

Hard question: when videos arrive across different phones, times of day,
weather, seasons, smoke/haze conditions, and construction stages, how will the
optimizer avoid melting geometry into floaters and color tearing? Flat
screen-space normalization is not enough.

Pass bar:

- Training uses per-image or per-sequence appearance embeddings and/or decoupled
  appearance fields, with transient/occluder modeling for cars, workers,
  fences, dumpsters, and vegetation.
- Captures are clustered by illumination and construction epoch before local
  optimization; cross-epoch fusion is geometry-first, appearance-second.
- The system keeps canonical geometry separate from time-varying appearance,
  temporary objects, and submitted-plan overlays.
- Quality gates track floaters, opacity mass outside parcel/prior bounds,
  photometric residuals by capture cohort, and geometry drift between epochs.

Primary references: Splatting in the Wild, DAVIGS, VastGaussian's decoupled
appearance modeling, and Mip-Splatting's aliasing analysis. Sources:
https://arxiv.org/abs/2403.10427, https://arxiv.org/abs/2501.10788,
https://arxiv.org/abs/2402.17427, https://niujinshuchong.github.io/mip-splatting/

### 4. Fill-rate overdraw, not only VRAM

Current state: `SplatRenderLayer` carefully manages GPU buffer residency, but
the pathological browser bottleneck for 10M translucent splats at pitch 85 is
often fill-rate and overdraw. Depth writes are disabled for correct blending,
and the fragment shader discards outside the ellipse, but every surviving
transparent fragment still participates in blending. The ring buffer solves
memory pressure; it does not prove pixel cost is bounded.

Hard question: what is the measured overdraw distribution per viewport,
especially on integrated GPUs and mobile? Are 60 fps failures caused by buffer
loads, CPU sort, texture composition, or alpha-blended fragment overdraw?

Pass bar:

- Add an overdraw debug mode that renders splats additively into an integer or
  color-coded heat buffer and reports p50/p95/p99 fragments per pixel.
- Profile with `EXT_disjoint_timer_query_webgl2` where available: traversal,
  upload, sort, texture, draw, and fragment time.
- Experiment with alpha-test/alpha-threshold variants, stochastic transparency,
  weighted blended OIT, depth prepass for opaque-enough surfels, and per-node
  screen-density caps.
- Establish device budgets: older iPhones/iPads, integrated Intel/Apple GPUs,
  low-memory Chromebooks, and common resident laptops.

Implementation warning: fragment `discard` can defeat early-Z on many GPU
pipelines, so "add a discard" is not automatically an optimization. This needs
real GPU timing, not intuition.

### 5. Async texture state and deterministic handoff

Current state: `NodeTextureManager` has generation guards and hysteresis, and
`SplatRenderLayer` snapshots/restores MapLibre GL state. That addresses some
known flicker paths. It does not yet prove that texture upload and binding are
deterministic under concurrent fetch/decode/compose completions.

Hard question: when `createImageBitmap` tasks resolve mid-frame, can a texture
state transition mutate the binding map while the draw loop is iterating? If
so, micro-stutters and one-frame texture pops can survive despite the generation
counter.

Pass bar:

- Texture acquisition uses a two-phase commit: async tasks produce immutable
  pending records; the render loop atomically swaps `pending -> ready` at a
  frame boundary.
- Each node has at most one texture generation visible to a frame; no mid-draw
  mutation of `bindings`.
- Add a stress test with delayed, shuffled tile promises, forced texture
  eviction, and camera sweeps to assert no state churn while draw calls execute.
- Record texture lifecycle counters in a debug HUD: requested, pending, ready,
  swapped, evicted, failed, reused, and re-uploaded.

### 6. ENU, Web Mercator, and projective texture drift

Current state: the render matrix uses MapLibre's Mercator matrix with a local
ENU scale, while `texturing.ts` converts ENU bbox to lon/lat through a linear
metres-per-degree approximation at the origin. That may be acceptable for small
nodes, but the mathematical error grows with distance from the origin and with
node size.

Hard question: what is the maximum pixel drift between projected orthophoto UVs
and true Web Mercator coordinates across all textured nodes? A shader should not
be doing full ellipsoidal transforms per fragment, but CPU-side linearization
must be quantified and bounded.

Pass bar:

- Precompute a per-node affine matrix `M_enu_to_tile_uv` on the CPU from the
  node's ENU corners converted through exact geodesy/Web Mercator, not from a
  global metres-per-degree approximation alone.
- Store the affine matrix in texture bindings and pass it to the shader, instead
  of `originEnu + invSizeEnu` when the node exceeds a drift threshold.
- Add tests that sample node corners and centers against exact lon/lat ->
  Mercator conversion and fail when drift exceeds, for example, 0.5 texel.
- Encode texture-drift max/mean in `manifest.json` or a texture QA artifact.

### 7. Spatiotemporal Parquet and 3D tile synchronization

Current state: the repo has a strong Parquet spatial store and a static web
export. The proposed Parquet civic event lake is necessary, but it creates a new
client problem: the map, vector events, 3D Tiles, picking index, and parcel
detail card must agree on the same snapshot.

Hard question: when a user pans the viewport, how does the frontend fetch event
logs, parcel vectors, and 3D geometry in one coherent execution context without
blocking the render loop or mixing vintages?

Pass bar:

- Every public artifact carries a `snapshot_id`: `parcels.geojson`,
  `details.json`, `summary.json`, `tileset.json`, `picking.json`, Parquet
  manifests, and STAC Items.
- The client uses a snapshot manifest to pin all fetches before drawing a
  parcel state; mixed-snapshot reads are allowed only with explicit stale labels.
- Heavy Parquet queries run in a Web Worker or server/edge worker, never on the
  render path.
- Viewport queries return a single bundle: APN set, civic events, spatial asset
  metadata, tile URLs, and source-health metadata.
- The UI has a deterministic downgrade path: if event logs lag 3D tiles, show
  geometry but mark civic status stale; if geometry lags events, show parcel
  status but mark spatial data stale.

### 8. Right-censoring and private cleanup opacity

Current state: the model already notes censoring, but opt-out/private cleanup is
not yet represented as a formal statistical state. For parcels outside public
debris/permit visibility, absence of evidence is not evidence of inactivity.

Hard question: how are private opt-outs represented in cohort velocity and
neighborhood baselines? If they are treated as "quiet" or "no activity," they
will bias velocity estimates downward and create unfair block-level narratives.

Pass bar:

- Add an explicit observation-state field per APN: publicly observed,
  privately managed/opaque, source-lagged, jurisdiction-coarse, resident-verified,
  or unknown.
- Treat private cleanups as right-censored/interval-censored observations in
  survival models, not as stalled events.
- Track proxy signals: grading permits, demolition/private haul permits,
  utility disconnect/reconnect, water/power/gas service work, temporary power
  poles, contractor notices, dumpsters/haul activity from imagery, resident
  attestations, and inspection requests.
- Report cohort metrics both with and without opaque parcels; show sensitivity
  intervals for neighborhood velocity.

Useful references: lifelines' survival modeling docs, competing-risk cautions,
and OCEL 2.0 for event logs where parcels, permits, inspections, contractors,
and utilities interact as distinct objects. Sources:
https://lifelines.readthedocs.io/en/latest/Survival%20analysis%20with%20lifelines.html,
https://www.publichealth.columbia.edu/research/population-health-methods/competing-risk-analysis,
https://www.ocel-standard.org/

### 9. Partial pooling without topographic erasure

Current state: hierarchical Bayesian partial pooling is the right instinct, but
the Palisades is not one homogeneous recovery process. Canyons, bluffs, coastal
constraints, landslide risk, road access, parcel slope, standard-plan
eligibility, and custom architecture all create different hazard functions.

Hard question: how does the model prevent over-smoothing a high-risk landslide
custom rebuild into a flat-lot standard-plan cohort? With neighborhood sample
sizes below five, naive sub-neighborhood pooling can be statistically invalid
and politically harmful.

Pass bar:

- Define cohorts by process mechanism, not only geography: slope/geology,
  coastal/bluff overlay, rebuild type, plan type, debris path, jurisdiction,
  permit path, utility dependency, and contractor availability.
- Use partial pooling with shrinkage diagnostics, posterior predictive checks,
  leave-one-neighborhood-out validation, and sensitivity reports.
- Suppress parcel-level ETA when posterior uncertainty is too wide; show the
  blockers and comparable-cases view instead.
- Never rank residents or neighborhoods by "slowness" without censoring and
  covariate adjustments.

### 10. Architectural plans as metric 3D anchors

Current state: the audit suggests using submitted plans, but that hides a hard
engineering problem. LADBS/ePlanLA handles electronic plan review and project
documents, but plan-check packages are usually PDF sheets, vector PDFs,
scanned/raster sheets, or CAD/BIM derivatives, not a clean CityGML/IFC model.
Multimodal models can label rooms, walls, and notes; they do not natively yield
survey-grade 3D constraints.

Hard question: how does openpali parse flat architectural PDFs into a
coordinate-calibrated 3D anchor before splat optimization begins?

Pass bar:

- Build a plan-ingestion pipeline with explicit sheet registration: detect title
  blocks, scale bars, north arrows, grid lines, dimensions, elevation datums,
  floor labels, section cuts, and revision clouds.
- Prefer vector extraction when PDFs preserve CAD primitives; fall back to
  raster/CV extraction only with lower confidence.
- Convert extracted elements into a typed intermediate schema: walls, openings,
  slabs, roof planes, stairs, retaining walls, floor elevations, massing
  envelope, setbacks, and source sheet references.
- Calibrate plan coordinates to APN geometry through parcel boundaries,
  foundation corners, street frontage, known setbacks, or submitted survey
  points; store the residual.
- Emit openBIM-compatible outputs where possible: IFC for building elements,
  CityGML-style LoD massing for city-scale context, and a lightweight
  parcel-local constraint graph for optimization.
- Every geometric primitive links back to sheet/page/scale/revision and carries
  confidence. The 3D engine may use low-confidence plan parses as soft priors,
  not hard truth.

Sources: LADBS ePlanLA/plan review pages describe electronic plan/document
submission; IFC is the buildingSMART/ISO open standard for machine-readable
built-asset descriptions; CityGML is the OGC 3D city-model standard. Sources:
https://dbs.lacity.gov/services/plan-review-permitting,
https://eplanla.lacity.org/, https://www.buildingsmart.org/standards/bsi-standards/industry-foundation-classes/,
https://www.ogc.org/standards/citygml/

### 11. Generative inpainting with structural truth constraints

Current state: generative models can make missing lots look complete or fill
uncaptured visual gaps, but a recovery tool must not hallucinate an invented
condition into an insurance, permitting, or contractor workflow.

Hard question: if 3D diffusion priors or conditional neural fields are used to
paint missing geometry, what prevents aesthetic filler from masquerading as a
real structure?

Pass bar:

- The product uses three distinct labels: observed, inferred from approved
  plans/records, and generatively visualized. These states must be visually and
  semantically impossible to confuse.
- Constrain generation with hard feasibility checks: parcel footprint, setbacks,
  maximum height, approved plan massing, roof/eave limits, floor elevations,
  slope/geology constraints, and known construction stage.
- Add explicit loss terms or wrappers:

  ```text
  L_total =
      lambda_photo L_rgb
    + lambda_prior L_geometry(Sigma_LARIAC, Sigma_plan)
    + lambda_text L_constraints(parcel, zoning, permit, plan)
    + lambda_sdf L_signed_distance_bounds
    + lambda_stage L_temporal_stage_consistency
    + lambda_unc L_uncertainty_penalty
  ```

- Hard constraints should be enforced by projection/repair steps or constrained
  optimization, not only by prompts. Examples: clip generated surfaces to the
  legal envelope, reject roof planes above approved height, and prevent interior
  features from appearing unless sourced from resident-permissioned plans or
  insurance files.
- Generated pixels/splats are never admissible as evidence. They are
  explanatory overlays only, with provenance and confidence.

### 12. Conflicting-source fusion and trust decay

Current state: the repo has LARIAC priors, aerial imagery, government event
feeds, and a planned resident capture stream. These sources will conflict:
pre-fire LiDAR shows an old house, mobile video shows framing, orthophotos show
temporary equipment, and satellite imagery may show roof-like shadows.

Hard question: when the local Gaussian optimizer sees conflicting evidence, how
does it decide whether to preserve stable prior geometry or adapt to new
on-site observations?

Pass bar:

- Each source has a covariance/trust model: spatial accuracy, temporal age,
  viewing angle, expected distortion, privacy/access class, legal reliability,
  and whether it describes planned, observed, or historical reality.
- Prior influence decays by physical state and time, not globally. LARIAC should
  remain strong for parcel frame, terrain, lot context, and pre-fire comparison,
  but weaken for rebuilt walls once resident/drone captures or approved plans
  provide newer evidence.
- Optimization uses source-specific weights:

  ```text
  L_total =
      lambda_photo(t, source) L_rgb
    + lambda_prior(t, state) L_geometry(Sigma_LARIAC)
    + lambda_plan L_plan_constraints
    + lambda_text L_record_constraints
    + lambda_temporal L_state_transition
    + lambda_conflict L_duplicate_or_blur_penalty
  ```

- Conflicts produce explicit branches when needed: "pre-fire baseline,"
  "approved design," "observed current state," and "temporary site objects."
  The model should not blend them into one blurry geometry layer.
- Add duplicate-geometry detectors: two parallel walls/roof planes within a
  small distance but from different epochs should trigger an epoch conflict, not
  be averaged.

### 13. Continuous spatiotemporal probability fields

Current state: the store has `t_epoch` per Gaussian, and web export produces a
static `.splat` pyramid. That is enough for snapshots, but not yet a true 4D
construction model.

Hard question: how does openpali represent "in-between" physical states, such
as partially completed framing, staged roof sheathing, or active foundation
forms, without swapping disconnected splat files?

Pass bar:

- Treat the parcel as a time-indexed probability field: occupancy/density,
  opacity, semantic class, confidence, and source support evolve over time.
- Store Gaussian/primitive lifespans: `valid_from`, `valid_to`, `observed_at`,
  `state_class`, `source_count`, and confidence. A splat can fade in/out as
  evidence accumulates rather than being deleted/replaced.
- Encode construction milestones as state-transition priors, not just labels.
  For example, foundation forms raise ground-plane occupancy before framing
  probabilities appear.
- Build temporal queries: "what did we know on this date?", "what changed since
  last week?", "which evidence changed this geometry?", and "what is
  uncertain?"
- The octree should support temporal filtering or per-node temporal summaries,
  so the client does not need to fetch every historical splat for a current
  view.

### 14. Hidden data constellations and permission boundaries

Current state: the pipeline is built mostly from public agency feeds and public
imagery. That is a good default for openness, but it leaves blind spots exactly
where residents most need help: interior loss, approved plan geometry, utility
readiness, and daily progress.

Hard question: which private or semi-private data sources can residents
permission into the system, and which sources require agency partnerships
rather than scraping?

Pass bar:

- **Insurance/Xactimate data.** Build a resident-permissioned vault for
  Xactimate/claims estimates, contents inventories, photos, scopes, and
  adjuster reports. Extract dimensions, materials, rooms, line items, and
  replacement assumptions into a private interior-spatial graph. This can seed
  claims support and interior reconstruction for homes with no public 3D prior.
  Source: Verisk describes Xactimate as property-claims estimating software:
  https://www.verisk.com/products/xactimate/

- **ePlanLA/CAD/BIM plan data.** Do not assume public scraping of login-gated
  ePlanLA documents is acceptable. Use resident authorization, contractor
  uploads, agency MOU, CPRA where applicable, or exported plan packages. If
  vector CAD/BIM layers are available, they should supersede PDF interpretation
  for foundation footprints, elevations, and massing.

- **Utility telemetry.** SCADA and grid energization logs can expose critical
  infrastructure and should require utility partnership, aggregation, and
  safety review. For resident-level energy/water/gas data, prefer
  resident-authorized Green Button/Connect My Data flows where available.
  Sources: https://www.energy.gov/data/green-button,
  https://www.greenbuttondata.org/cmd.html

- **Commercial satellite tasking.** Add a change-detection layer for high-value
  parcels/blocks using daily or high-revisit commercial imagery where budget
  permits. Planet documents SkySat as 50 cm orthorectified high-resolution
  imagery with high-revisit tasking. Use it to trigger "site changed" alerts,
  not to overclaim fine 3D geometry. Source:
  https://docs.planet.com/data/imagery/skysat/

- **Contractor and supply-chain data.** Resident-permissioned contracts,
  schedules, invoices, inspection requests, lien notices, and material delivery
  dates are often better predictors of progress than public permits alone.

- **Privacy model.** Every private source must have consent, revocation,
  retention, encryption, access scopes, and explicit publication rules. The
  default public product should show derived aggregate status, not private
  documents or interior details.

## State of the art and what to adopt

### 1. City-scale 3D Gaussian Splatting

The original 3DGS paper established real-time 1080p rendering with anisotropic
Gaussians optimized from calibrated images, but large outdoor scenes need
different machinery. The most relevant work for openpali is:

- Hierarchical 3D Gaussians: divide-and-conquer training and LOD hierarchies for
  scenes with tens of thousands of images and kilometer-scale trajectories.
  Source: https://arxiv.org/abs/2406.12080
- CityGaussian: global scene priors, adaptive data selection, block-level LOD,
  and real-time large-scale rendering. Source: https://arxiv.org/abs/2404.01133
- VastGaussian: progressive partitioning, airspace-aware visibility, parallel
  optimization, and decoupled appearance modeling for large scenes. Source:
  https://arxiv.org/abs/2402.17427
- Octree-GS: LOD-structured Gaussians for consistent speed under zoom-out and
  dense-frustum views. Source: https://arxiv.org/abs/2403.17898
- GigaGS: planar-based 3DGS for large-scale surface reconstruction, useful where
  dimensional surfaces matter more than pure view synthesis. Source:
  https://arxiv.org/abs/2409.06685
- LSG-SLAM: large-scale outdoor stereo 3DGS SLAM with submaps, loop closure,
  feature-warping losses, and KITTI evaluation. Source:
  https://arxiv.org/abs/2505.09915

Implementation direction: keep the existing 3D Tiles-style web pyramid, but add
a training pipeline that partitions captures into APN/H3/submap chunks, trains
local GS models with appearance embeddings, and publishes confidence-scored
temporal deltas rather than replacing the whole map.

### 2. Semantic and open-vocabulary splats

A civic 3D twin should be queryable: "show foundations poured this month",
"show overhead power conflicts", "show lots with retaining-wall activity", or
"show visible debris piles near my block." Recent semantic 3DGS work can turn
the viewer into an inspection and search layer:

- Semantic Gaussians distills 2D pretrained image features into 3D Gaussians for
  open-vocabulary scene understanding. Source: https://arxiv.org/abs/2403.15624
- SuperGSeg uses structured super-Gaussians to reduce memory cost for language
  features and segmentation. Source: https://arxiv.org/abs/2412.10231
- Segment then Splat segments object sets before reconstruction, reducing
  cross-view inconsistency. Source: https://arxiv.org/abs/2503.22204
- CAGS adds local graph context to reduce SAM-derived granularity inconsistency.
  Source: https://arxiv.org/abs/2504.11893

Implementation direction: add a separate semantic asset tier, not bloated render
splats. Store per-object/per-surface embeddings keyed to APN, time, source, and
confidence. Render only selected semantic overlays.

### 3. Hybrid geometry: 3DGS plus measurable surfaces

Gaussian splats are excellent for visual communication, but residents,
contractors, insurers, and city reviewers need measurable evidence. openpali
should pair 3DGS with:

- photogrammetric meshes/point clouds for dimensions and change detection;
- 2D/3D Gaussian surface reconstruction where surfaces matter;
- parcel-local control points and uncertainty ellipsoids;
- pre/post DEM differencing for debris, grading, retaining walls, and pad
  readiness;
- optional mesh extraction from splats for contractor and insurance exports.

Useful frameworks: COLMAP/OpenSfM for pose/SfM, OpenDroneMap/WebODM for
orthomosaics and point clouds, Nerfstudio for research pipelines, and gsplat for
optimized Gaussian training. Sources: https://arxiv.org/abs/2302.04264 and
https://arxiv.org/abs/2409.06765

### 4. Standards-first spatial data

The project is already close to the right geospatial standards. Tighten it:

- GeoParquet 1.1 requires `geo` metadata, geometry encodings, CRS metadata, and
  can use bbox covering columns for query acceleration. Source:
  https://geoparquet.org/releases/v1.1.0/
- STAC should catalog each imagery/splat/point-cloud acquisition with time,
  geometry, license, platform, processing level, source hash, and links. Source:
  https://github.com/radiantearth/stac-spec
- 3D Tiles is designed for massive heterogeneous 3D geospatial streaming with
  HLOD, screen-space error, metadata, and implicit tiling. Source:
  https://github.com/CesiumGS/3d-tiles/tree/main/specification
- OGC API Features gives a standard HTTP shape for queryable feature
  collections. Source: https://docs.ogc.org/is/17-069r4/17-069r4.html
- Overture Maps publishes cloud-hosted GeoParquet, stable GERS IDs, and a STAC
  release catalog; use it to enrich addresses, buildings, roads, and POIs where
  licensing permits. Source: https://docs.overturemaps.org/

Implementation direction: create `data/catalog/stac/` and emit STAC Items for
every public/private spatial artifact. Add GeoParquet bbox columns to
`assets.parquet`. Preserve the static site export, but make it a derived
publication from a queryable lake.

### 5. Robust civic data pipeline

The current Python ETL is understandable and good for bootstrap. Production
should adopt asset-oriented orchestration and explicit data-quality checks:

- Dagster assets model persisted tables/files/models as first-class assets with
  dependencies and materializations. Source:
  https://docs.dagster.io/guides/build/assets
- Great Expectations supports explicit data expectations, validation results,
  severity, suites, and checkpoints. Source:
  https://docs.greatexpectations.io/docs/core/introduction/try_gx/
- OpenLineage defines an open lineage model for jobs, runs, datasets, and
  extensible facets. Source: https://openlineage.io/docs/
- Apache Iceberg adds schema evolution, hidden partitioning, time travel,
  rollback, serializable isolation, and concurrent writes for lake tables.
  Source: https://iceberg.apache.org/docs/latest/

Implementation direction: preserve `uv run run.py` for local use, but wrap
fetch, normalize, validate, score, emit, and spatial export as assets. Every
asset gets source query params, raw hash, schema hash, run id, and validation
status. Publish public JSON only after checks pass.

### 6. Modeling rebuild time and policy impact

The current score is a communication score, not a policy model. Add a separate
analytics layer:

- Event-log schema: APN, case id, event type, department, timestamp, source,
  actor class, jurisdiction, policy regime, document completeness, corrections,
  inspection result, and next required action.
- Survival/time-to-event models: plan-submit to plan-approval, approval to
  issued, issued to first inspection, inspection milestones, final to CofO.
- Competing risks: insurance delay, utility readiness, debris, grading/geology,
  coastal/bluff/biological clearance, contractor availability.
- Hierarchical Bayesian partial pooling: parcel, neighborhood, jurisdiction,
  project type, hillside/coastal status, rebuild type, and policy cohort.
- Process mining: discover actual bottleneck paths from event logs rather than
  trusting the official process diagram.
- Causal policy evaluation: difference-in-differences/synthetic-control style
  comparisons for EO1, EO6 self-certification, EO8, standard plans, AI pre-plan
  check, and future fee/clearance reforms.
- Fairness audits: compare delays by ZIP, structure type, owner-occupied vs
  rental proxy, language-access indicators, age/disability vulnerability
  proxies, insurance type, and whether the parcel is in City LA, Malibu, or
  unincorporated county.

Methodological caution: public-sector predictions can change behavior. Show
uncertainty and explanations, not deterministic dates. Recent fairness work
warns that static fairness criteria can have delayed impacts; time-to-event
fairness is an active research area. Sources:
https://arxiv.org/abs/1803.04383 and https://arxiv.org/abs/2605.11362

### 7. Resident AI services

Build agents as "cited copilots" rather than autonomous legal actors. The
highest-value workflows are:

- Insurance claim builder: contents inventory, comparable replacement costs,
  photo/receipt extraction, adjuster letter drafts, discrepancy tracker,
  deadline calendar, and evidence bundle export.
- Permit navigator: eligibility classifier for like-for-like/EO1, EO8,
  self-certification, standard plans, required clearances, missing docs, and
  next-action checklists.
- Contractor coordinator: bid normalization, license/complaint checks, scope
  comparisons, schedule-risk tracking, change-order diffing, lien-warning
  explanations, and payment milestone reminders.
- Policy-defense agent: appeal packets for overgrown-lawn tickets,
  reassessments, AV/property-tax issues, hydrant/utility fees, debris charges,
  and city-service failures.
- Neighborhood intelligence: block-level shared timelines, anonymous issue
  aggregation, contractor waitlists, utility bottlenecks, and "what worked for
  a similar parcel" retrieval.

Guardrails:

- cite every claim to official records, uploaded documents, or named public
  sources;
- require user approval before sending anything;
- label legal/insurance/tax content as assistance, not professional advice;
- route complex matters to licensed counsel/public adjusters/engineers;
- keep private documents encrypted and scoped to the resident's household or
  invited collaborators;
- record an evidence trail for every generated packet.

### 8. Product features with outsized community value

1. **Parcel truth card.** One page per APN with official status, source dates,
   confidence, missing data, neighbor cohort, pending blockers, and "what you
   can do next."

2. **Coverage honesty layer.** Show whether the 3D parcel is LARIAC prior,
   footprint extrusion, resident capture, drone capture, official inspection,
   stale, or missing.

3. **Rebuild blockers heatmap.** Separate "no application," "in corrections,"
   "waiting utility," "waiting inspection," "insurance unresolved," "geology,"
   and "contractor inactive."

4. **Permit correction corpus.** OCR plan-check correction letters, cluster
   them, and identify recurring ambiguous rules that should be clarified or
   waived.

5. **Policy simulator.** Estimate saved days if a clearance is removed,
   self-certification is expanded, standard plans are adopted, or inspection
   staffing changes.

6. **Neighborhood convoy planning.** If multiple homes need the same trade,
   utility reconnection, debris haul, geotech, or inspection type, coordinate
   block-level sequencing.

7. **Before/after/next slider.** Pre-fire LARIAC/Wayback, post-fire orthos,
   current county imagery, submitted plan massing, and predicted/actual
   construction state.

8. **Resident capture app.** Guided mobile capture with privacy masking, APN
   consent, geofence warnings, quality scoring, and upload-to-reconstruction.

9. **Contractor risk graph.** License status, bonds, complaints, permit
   velocity, inspection pass rates, neighborhood references, and schedule
   reliability.

10. **Civic data FOIA/CPRA assistant.** Generate precise records requests for
    missing datasets, hydrant logs, inspection staffing, plan-check queues, and
    utility restoration records.

## Immediate implementation roadmap

### Next 2 weeks

- Add a public `coverage.json`: APN -> civic status, spatial status,
  `n_splats`, geometry source, acquisition date, confidence, and missing reason.
- Make all cold-start priors renderable: convert footprint-extrusion
  `mesh_vertices` into splats or emit a polygon-prism fallback layer for all
  717 `static_baseline` lots and any LARIAC-missing parcels.
- Add an observation-state field to the civic artifacts: public, private
  opt-out/opaque, jurisdiction-coarse, source-lagged, resident-verified,
  unknown.
- Add source hash/schema hash/run id to every `meta.json` source entry.
- Add Great Expectations or lightweight equivalent checks for APN parse rate,
  row counts, duplicate APNs, missing geometry, status taxonomy drift, and
  official-count reconciliation.
- Add UI labels for `static_baseline`, stale, footprint fallback, and no-splat
  parcels.
- Code split the web app so 3D renderer/texturing loads only when the 3D mode is
  opened.
- Add renderer instrumentation: draw-list size, resident bytes, sort time,
  texture state counters, overdraw heatmap mode, and GPU timing where
  `EXT_disjoint_timer_query_webgl2` is available.

### Next 30-45 days

- Convert civic event output into Parquet/GeoParquet event tables alongside the
  JSON export.
- Add STAC catalog generation for imagery, LARIAC extracts, splat tiles,
  orthos, and resident/private captures.
- Add `snapshot_id` across civic JSON, tile manifests, picking index, Parquet
  outputs, and STAC Items so the frontend can pin coherent dataset vintages.
- Replace texture-origin/inverse-size projection with a per-node
  `M_enu_to_tile_uv` affine matrix whenever exact-corner Mercator drift exceeds
  0.5 texel.
- Add two-phase texture publication: async compose writes pending records; the
  render loop atomically swaps them at frame boundaries.
- Build the first survival model with uncertainty bands and backtesting by
  withholding old events.
- Treat private cleanup and source-opaque parcels as censored observations; ship
  public metrics with sensitivity intervals.
- Add a resident correction workflow: report bad APN join, missing permit,
  wrong address, or stale official link.
- Build "permit packet assistant v0" using retrieval over official LA rebuild
  rules and user-uploaded documents.
- Start plan-package ingestion: accept resident/contractor-uploaded PDFs,
  vector PDFs, DWG/DXF exports, IFC, and image sheets; extract sheet scale,
  dimensions, elevations, and massing constraints into a typed plan graph.
- Define a source-trust schema for LARIAC, plans, mobile captures, orthos,
  satellite imagery, insurance files, utilities, and resident attestations:
  covariance, age, observation/planned/historical semantics, privacy class, and
  allowed publication level.

### Next 90 days

- Implement capture ingestion: upload, EXIF/GPS validation, pose estimation,
  privacy redaction, APN consent, reconstruction queue, confidence scoring, and
  temporal publication.
- Require a capture-observability gate before reconstruction: prior availability,
  parallax, loop closure, GPS dispersion, texture richness, and anchor/control
  count.
- Train local APN/H3 3DGS chunks using gsplat/Nerfstudio-style pipelines and
  compare against LARIAC priors.
- Add appearance-conditioned reconstruction: per-image embeddings, illumination
  clustering, transient-object suppression, and epoch-aware geometry/appearance
  separation.
- Add constraint-conditioned reconstruction: plan envelope, zoning/setback,
  max-height, floor-elevation, and permit-stage losses; generated/inpainted
  geometry remains labeled non-evidentiary.
- Extend the spatial schema for temporal probability fields: primitive
  lifespans, source support, confidence, semantic state, and temporal
  query/export paths.
- Build a measurable-geometry pipeline: MVS/depth fusion -> TSDF/SDF volume ->
  Marching Cubes mesh -> measurement uncertainty -> resident/contractor export.
- Add process-mining analytics for plan-check and inspection bottlenecks.
- Launch policy simulator with transparent assumptions and exportable charts.
- Create a secure resident vault for insurance/permit/contractor documents.
- Pilot data-blending partnerships or resident-consent flows for Xactimate/
  claims estimates, ePlanLA/exported CAD/BIM packages, Green Button utility
  data, and commercial satellite change detection.

## Research bets

- **City-scale temporal GS as civic infrastructure.** Treat each parcel as a
  small evolving scene registered to a stable municipal prior, then stitch
  parcels into neighborhood submaps. This is more feasible than a monolithic
  city 3DGS and aligns with APN-based permissions.

- **Policy-aware survival modeling.** The rebuild is a natural experiment across
  jurisdictions, executive orders, self-certification, standard plans, coastal
  constraints, and utility readiness. A careful model could identify reforms
  that save months without reducing safety.

- **Open-vocabulary 3D civic search.** Semantic splats can make the 3D model
  useful for inspections, resident questions, and community reporting, not just
  visualization.

- **Evidence-first agents.** The killer AI product is not a chatbot; it is an
  evidence compiler that makes residents harder to ignore by insurers,
  contractors, and agencies.

- **Community data trust layer.** Public records plus resident corrections plus
  private evidence, each with permissioned provenance, can become a defensible
  shared memory of the rebuild.

## Source notes

Important current official context:

- LA City says Palisades rebuilds have one-stop support centers, reduced
  clearances, AI pre-plan check, standard plans, self-certification, and
  executive-order paths. Source: https://recovery.lacity.gov/rebuilding
- LA County publishes a permitting progress dashboard and related city-resource
  links. Source:
  https://recovery.lacounty.gov/rebuilding/permitting-progress-dashboard/
- MyLA311 is the resident channel for many city services and requests. Source:
  https://lacity.gov/myla311

This audit should be revisited whenever LADBS, LA County, Malibu, LARIAC, or
state insurance rules change.
