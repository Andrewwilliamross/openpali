# SPATIAL-002 renderer benchmark baseline + improvement selection

Job: `renderer-bench` (deterministic scene pair, fixed cameras, 640x400,
frame-count sampling), run in-cluster via the wrapper. Exit 0, 1 passed.

    gl_renderer: ANGLE (Vulkan SwiftShader / LLVM 10) — hardware_accelerated: FALSE
    (correctness + relative-regression evidence only; no GPU claims)

    scene            frames p50_ms  p95_ms  splats/frame nodes/frame resident_mb requests
    top-down-far     13     1816.6  3049.9  217,559      133         20.9        52
    usgs-aoi-medium  15     1866.6  2366.6  180,160      98          35.1        0

## Profiling-selected improvement (predeclared before implementation)

The FAR scene (whole footprint visible, z13.2, pitch 0) draws MORE splat
instances per frame (217k) than the close-up medium scene (180k): the fixed
SSE_THRESHOLD_PX=14 admits deep LOD levels for hundreds of small on-screen
nodes at wide views — maximal overdraw where per-splat contribution is
smallest. Selected improvement: a PER-FRAME SPLAT BUDGET — when the SSE
traversal's selected content exceeds the budget, re-traverse with a scaled
threshold so wide views resolve to coarser (faithful, energy-conserving)
LOD representatives. Expected effect: large splats/frame reduction on wide
scenes with unchanged near-view quality; measured before/after on THIS
deterministic pair; correctness guarded by the existing e2e spatial spec
(draws, picking, labels) and coverage reconciliation.

Baseline for the before/after: this file. The improvement lands in
SplatRenderLayer.render() traversal only (no tiler/format change).

## AFTER (same job, same scenes, budget=150k active; e2e gate 2/2 green)

    scene            frames p50_ms  splats/frame nodes/frame resident_mb
    top-down-far     13     2016.6  164,498      108         18.9
    usgs-aoi-medium  15     2150.0  169,049      86          31.6

Measured effect: wide-scene instanced draws -24.4% (217,559 -> 164,498),
nodes -19%, resident GPU bytes -10%; correctness/coverage unchanged (spatial
e2e spec 2/2: draws, picking, labels; medium scene barely touched, -6%).
HONEST scoping: p50 frame time on SwiftShader moved +11%/+15% — software
rasterization is FILL-bound (coarser cut = fewer but larger quads covering
similar pixels) and 13-15 samples carry high run variance (p95 ~unchanged).
The instance/vertex/sort-side win this targets applies to hardware GPUs;
claiming a frame-time improvement requires a HEADED run on real hardware,
recorded as a human-runnable follow-up — per the acceptance rule that
headless/software supports correctness, never GPU-performance claims.

## AFTER v2 (repair round 4: cross-frame hysteresis replaces the same-frame
## re-traversal; single traversal per frame; e2e gate 13/13 green)

    scene            frames p50_ms  p95_ms  splats/frame nodes/frame resident_mb
    top-down-far     11     2316.5  2866.6  199,790      104         18.2
    usgs-aoi-medium  15     1600.0  1666.6  156,934      87          31.6

Measured effect vs the same-frame retraversal version: the double traversal
is gone; the MEDIUM scene now runs BELOW the pre-budget baseline on both
splats/frame (156,934 vs 180,160, -13%) and SwiftShader p50 (1600.0 vs
1866.6, -14%; p95 1666.6 vs 2366.6). The WIDE scene converges toward the
budget across frames by design (x1.5 threshold steps): 11 slow SwiftShader
frames only reach 199,790 splats/frame (-8% vs pre-budget; the retraversal
version reached 164k instantly but paid a p50 penalty every frame). Same
honest scoping as above: SwiftShader timings support relative regression
evidence only, never GPU claims.
