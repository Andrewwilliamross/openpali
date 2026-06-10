"""Spatial core: spatiotemporal schema, 3D ingestion, registration, LOD tiling.

Modules
-------
geodesy       exact coordinate transforms (WGS84 ⇄ ECEF ⇄ ENU, EPSG:2229 → WGS84)
schema        the unified spatiotemporal state model + partitioned GeoParquet store
scene_client  LARIAC 3D building extraction (SceneServer / extruded-footprint prior)
registration  rigid alignment: SOR → Mahalanobis gating → RANSAC coarse → ICP fine
splat_tiler   hierarchical 3DGS octree LOD → 3D Tiles 1.1 + streamable .splat tiles
runner        idempotent nightly orchestration over the full destroyed-parcel universe
"""
