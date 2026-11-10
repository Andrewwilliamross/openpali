// Frustum extraction + screen-space-error (SSE) refinement for octree traversal.
//
// Planes are extracted Gribb–Hartmann style from a combined (projection·view)
// matrix: each plane is row4 ± rowN of the matrix, valid for any matrix that
// maps world → clip, which is exactly what MapLibre hands custom layers.

import type { Mat4 } from './mat4'

export interface Plane {
  nx: number
  ny: number
  nz: number
  d: number
}

/** Extract the 6 frustum planes (normalized) from a world→clip matrix.
 *  Row-extraction on a column-major matrix: row(i)[j] = m[j*4 + i]. */
export function extractFrustumPlanes(m: Mat4): Plane[] {
  const row = (i: number): [number, number, number, number] =>
    [m[i], m[4 + i], m[8 + i], m[12 + i]]
  const r0 = row(0), r1 = row(1), r2 = row(2), r3 = row(3)
  const raw: [number, number, number, number][] = [
    [r3[0] + r0[0], r3[1] + r0[1], r3[2] + r0[2], r3[3] + r0[3]], // left
    [r3[0] - r0[0], r3[1] - r0[1], r3[2] - r0[2], r3[3] - r0[3]], // right
    [r3[0] + r1[0], r3[1] + r1[1], r3[2] + r1[2], r3[3] + r1[3]], // bottom
    [r3[0] - r1[0], r3[1] - r1[1], r3[2] - r1[2], r3[3] - r1[3]], // top
    [r3[0] + r2[0], r3[1] + r2[1], r3[2] + r2[2], r3[3] + r2[3]], // near
    [r3[0] - r2[0], r3[1] - r2[1], r3[2] - r2[2], r3[3] - r2[3]], // far
  ]
  return raw.map(([a, b, c, d]) => {
    const len = Math.hypot(a, b, c) || 1
    return { nx: a / len, ny: b / len, nz: c / len, d: d / len }
  })
}

/** Sphere-vs-frustum: true when the sphere intersects or is inside. */
export function sphereInFrustum(planes: Plane[], cx: number, cy: number,
                                cz: number, r: number): boolean {
  for (const p of planes) {
    if (p.nx * cx + p.ny * cy + p.nz * cz + p.d < -r) return false
  }
  return true
}

/**
 * Screen-space error in pixels for a node, the 3D-Tiles way:
 *
 *   sse = geometricError · viewportHeight / (distance · 2 · tan(fovY/2))
 *
 * `distance` is camera→node-boundary distance in the same units as
 * geometricError (metres for us). Perspective handles the horizon naturally:
 * far canyon nodes get tiny SSE and keep their coarse LOD even at high pitch.
 */
export function screenSpaceError(geometricError: number, distance: number,
                                 viewportHeight: number, fovYRadians: number): number {
  if (geometricError <= 0) return 0
  const d = Math.max(distance, 0.1)
  return (geometricError * viewportHeight) / (d * 2 * Math.tan(fovYRadians / 2))
}

/** Distance from a point to an AABB (0 when inside). */
export function pointToBoxDistance(px: number, py: number, pz: number,
                                   minX: number, minY: number, minZ: number,
                                   maxX: number, maxY: number, maxZ: number): number {
  const dx = Math.max(minX - px, 0, px - maxX)
  const dy = Math.max(minY - py, 0, py - maxY)
  const dz = Math.max(minZ - pz, 0, pz - maxZ)
  return Math.hypot(dx, dy, dz)
}

/** Ray vs axis-aligned box (slab method). Returns entry t ≥ 0 or null. */
export function rayBoxIntersect(ox: number, oy: number, oz: number,
                                dx: number, dy: number, dz: number,
                                minX: number, minY: number, minZ: number,
                                maxX: number, maxY: number, maxZ: number): number | null {
  let tmin = -Infinity
  let tmax = Infinity
  const axes: [number, number, number, number][] = [
    [ox, dx, minX, maxX],
    [oy, dy, minY, maxY],
    [oz, dz, minZ, maxZ],
  ]
  for (const [o, d, lo, hi] of axes) {
    if (Math.abs(d) < 1e-12) {
      if (o < lo || o > hi) return null
      continue
    }
    let t1 = (lo - o) / d
    let t2 = (hi - o) / d
    if (t1 > t2) {
      const t = t1
      t1 = t2
      t2 = t
    }
    tmin = Math.max(tmin, t1)
    tmax = Math.min(tmax, t2)
    if (tmin > tmax) return null
  }
  if (tmax < 0) return null
  return tmin >= 0 ? tmin : 0
}
