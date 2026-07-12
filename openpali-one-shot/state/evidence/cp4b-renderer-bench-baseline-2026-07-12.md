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
