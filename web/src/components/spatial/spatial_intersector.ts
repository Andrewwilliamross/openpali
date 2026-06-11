// 3D asset → parcel picking.
//
// Raw Gaussian fields aren't selectable, so picking goes through the LARIAC
// bounding prisms: each APN's splats were boxed in the tileset's ENU frame at
// export time (picking.json). A click becomes a world ray (screen → NDC →
// inverse ENU matrix), intersected against every prism (slab method); the
// nearest hit wins. ~5k AABB tests per click is microseconds — no BVH needed.

import type { Map as MLMap, PointLike } from 'maplibre-gl'
import { rayBoxIntersect } from './frustum'
import { invert, transformPoint, type Mat4 } from './mat4'
import { composeTRS } from './mat4'
import type { CustomRenderMethodInput } from 'maplibre-gl'

export interface PickEntry {
  bbox: [number, number, number, number, number, number] // ENU min xyz / max xyz
  lon: number
  lat: number
  n: number
}

export type PickingIndex = Record<string, PickEntry>

export interface PickHit {
  apn: string
  distance: number
  lon: number
  lat: number
}

export class SpatialIntersector {
  private index: PickingIndex = {}
  private lastEnuMatrix: Mat4 | null = null
  private loaded = false

  async load(baseUrl: string): Promise<void> {
    try {
      const resp = await fetch(`${baseUrl.replace(/\/$/, '')}/picking.json`)
      if (!resp.ok) return
      this.index = (await resp.json()) as PickingIndex
      this.loaded = true
    } catch {
      this.loaded = false
    }
  }

  get ready(): boolean {
    return this.loaded
  }

  private originAltAMSL = 0

  /** Called by the splat layer each frame so picks use the live camera. */
  updateMatrix(args: CustomRenderMethodInput,
               originMerc: { x: number; y: number; z: number },
               metersToMerc: number, originAltAMSL = 0): void {
    const main = args.defaultProjectionData.mainMatrix as unknown as ArrayLike<number>
    const m = new Float64Array(16)
    for (let i = 0; i < 16; i++) m[i] = main[i]
    this.lastEnuMatrix = composeTRS(
      m, [originMerc.x, originMerc.y, originMerc.z],
      [metersToMerc, -metersToMerc, metersToMerc])
    this.originAltAMSL = originAltAMSL
  }

  /**
   * Screen point → ENU ray → nearest APN prism hit.
   * The prism is expanded ±6 m vertically to absorb terrain-clamp offsets.
   */
  pick(map: MLMap, point: PointLike): PickHit | null {
    if (!this.loaded || !this.lastEnuMatrix) return null
    const inv = invert(this.lastEnuMatrix)
    if (!inv) return null
    const p = Array.isArray(point) ? { x: point[0], y: point[1] } : point as { x: number; y: number }
    const canvas = map.getCanvas()
    const dpr = canvas.width / canvas.clientWidth
    const ndcX = ((p.x * dpr) / canvas.width) * 2 - 1
    const ndcY = -(((p.y * dpr) / canvas.height) * 2 - 1)

    // unproject two depths to form the ray in ENU space
    const a = transformPoint(inv, [ndcX, ndcY, -0.95])
    const b = transformPoint(inv, [ndcX, ndcY, 0.95])
    const ox = a[0]
    const oy = a[1]
    const oz = a[2]
    let dx = b[0] - a[0]
    let dy = b[1] - a[1]
    let dz = b[2] - a[2]
    const len = Math.hypot(dx, dy, dz) || 1
    dx /= len
    dy /= len
    dz /= len

    // The renderer clamps splats to the terrain skin (per-node z offset), so
    // the baked prisms must be shifted the same way before ray testing. The
    // shift is parcel-anchored: terrain elevation at the parcel minus the
    // parcel's baked base — the same formula the render layer applies, with a
    // small residual margin for intra-node relief.
    const RESIDUAL_M = 4
    let best: PickHit | null = null
    for (const [apn, e] of Object.entries(this.index)) {
      const [minX, minY, minZ, maxX, maxY, maxZ] = e.bbox
      let elev: number | null = null
      try {
        elev = map.queryTerrainElevation([e.lon, e.lat])
      } catch {
        elev = null
      }
      const baseAMSL = this.originAltAMSL + minZ
      const zShift = elev === null ? -baseAMSL : elev - baseAMSL
      const t = rayBoxIntersect(ox, oy, oz, dx, dy, dz,
        minX, minY, minZ + zShift - RESIDUAL_M,
        maxX, maxY, maxZ + zShift + RESIDUAL_M)
      if (t !== null && (best === null || t < best.distance)) {
        best = { apn, distance: t, lon: e.lon, lat: e.lat }
      }
    }
    return best
  }
}
