/**
 * Lazy entry point for the 3D renderer subsystem (ROADMAP D10 / PR3).
 *
 * MapView dynamic-imports this module on first 3D entry, so the splat
 * renderer, shaders, texturing, tileset streaming, and ray-pick code are
 * code-split out of the core bundle. 2D sessions never download them.
 *
 * Do not import this module statically from anything in the main graph —
 * that would pull the whole subsystem back into the core chunk.
 */
export { SplatRenderLayer } from './SplatRenderLayer'
export { SpatialIntersector } from './spatial_intersector'
