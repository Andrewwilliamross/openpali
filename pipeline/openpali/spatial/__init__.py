"""Rights-safe versioned spatial asset pipeline (SPATIAL-001).

Acquisition -> immutable raw objects -> asset registry -> CRS/vertical-datum
normalization -> derived terrain + surfel tiles -> release selection -> API ->
renderer. Every asset version carries acquisition/vintage, observation kind,
CRS/datum, transform lineage, coverage, quality, and rights state; processing
time is never presented as acquisition time.
"""
