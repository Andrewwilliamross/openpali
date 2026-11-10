import { describe, expect, it } from 'vitest'
import { composeTRS, identity, invert, multiply, transformPoint } from '../mat4'
import {
  extractFrustumPlanes,
  pointToBoxDistance,
  rayBoxIntersect,
  screenSpaceError,
  sphereInFrustum,
} from '../frustum'

// a plausible perspective·view matrix (column-major), fovY 60°, looking down -z
function perspectiveView(): Float64Array {
  const f = 1 / Math.tan(Math.PI / 6)
  const aspect = 16 / 9
  const near = 1
  const far = 5000
  const p = new Float64Array(16)
  p[0] = f / aspect
  p[5] = f
  p[10] = (far + near) / (near - far)
  p[11] = -1
  p[14] = (2 * far * near) / (near - far)
  // camera at (0, 0, 100) looking down -z: view = T(0,0,-100)
  const v = identity()
  v[14] = -100
  return multiply(p, v)
}

describe('mat4', () => {
  it('invert · multiply round-trips to identity', () => {
    const m = perspectiveView()
    const inv = invert(m)
    expect(inv).not.toBeNull()
    const id = multiply(m, inv as Float64Array)
    for (let i = 0; i < 16; i++) {
      expect(id[i]).toBeCloseTo(i % 5 === 0 ? 1 : 0, 9)
    }
  })

  it('transformPoint applies perspective divide', () => {
    const m = perspectiveView()
    const [x, y] = transformPoint(m, [0, 0, 0]) // 100 in front of camera
    expect(x).toBeCloseTo(0, 9)
    expect(y).toBeCloseTo(0, 9)
  })

  it('composeTRS matches manual transform order (translate then scale)', () => {
    const m = perspectiveView()
    const composed = composeTRS(m, [10, 20, 30], [2, -2, 2])
    const p: [number, number, number] = [1, 2, 3]
    const direct = transformPoint(m, [10 + 2 * 1, 20 + -2 * 2, 30 + 2 * 3])
    const viaCompose = transformPoint(composed, p)
    for (let i = 0; i < 3; i++) expect(viaCompose[i]).toBeCloseTo(direct[i], 9)
  })
})

describe('frustum', () => {
  it('center point is inside, far-behind point is culled', () => {
    const planes = extractFrustumPlanes(perspectiveView())
    expect(sphereInFrustum(planes, 0, 0, 0, 1)).toBe(true) // in front of cam
    expect(sphereInFrustum(planes, 0, 0, 200, 1)).toBe(false) // behind camera
    expect(sphereInFrustum(planes, 100000, 0, 0, 1)).toBe(false) // far left
  })

  it('big spheres straddling planes survive', () => {
    const planes = extractFrustumPlanes(perspectiveView())
    expect(sphereInFrustum(planes, 0, 0, 150, 80)).toBe(true) // overlaps near plane
  })

  it('SSE shrinks with distance and grows with geometric error', () => {
    const fov = Math.PI / 3
    const near = screenSpaceError(8, 100, 1080, fov)
    const far = screenSpaceError(8, 2000, 1080, fov)
    expect(near).toBeGreaterThan(far)
    expect(screenSpaceError(16, 100, 1080, fov)).toBeCloseTo(near * 2, 6)
    // a leaf (error 0) never refines
    expect(screenSpaceError(0, 1, 1080, fov)).toBe(0)
  })

  it('ray hits and misses boxes correctly (slab method)', () => {
    // ray along +x hits a unit box at x∈[5,6]
    const t = rayBoxIntersect(0, 0.5, 0.5, 1, 0, 0, 5, 0, 0, 6, 1, 1)
    expect(t).toBeCloseTo(5, 9)
    // ray pointing away misses
    expect(rayBoxIntersect(0, 0.5, 0.5, -1, 0, 0, 5, 0, 0, 6, 1, 1)).toBeNull()
    // ray origin inside the box returns t=0
    expect(rayBoxIntersect(5.5, 0.5, 0.5, 1, 0, 0, 5, 0, 0, 6, 1, 1)).toBe(0)
    // axis-parallel ray outside the slab misses
    expect(rayBoxIntersect(0, 5, 0.5, 1, 0, 0, 5, 0, 0, 6, 1, 1)).toBeNull()
  })

  it('point-to-box distance is 0 inside and Euclidean outside', () => {
    expect(pointToBoxDistance(0.5, 0.5, 0.5, 0, 0, 0, 1, 1, 1)).toBe(0)
    expect(pointToBoxDistance(4, 0, 0, 0, -1, -1, 1, 1, 1)).toBeCloseTo(3, 9)
  })
})
