import { describe, expect, it } from 'vitest'
import { composeTRS, identity, invert, multiply, transformPoint } from '../mat4'
import {
  extractFrustumPlanes,
  pointToBoxDistance,
  rayBoxIntersect,
  screenSpaceError,
  sphereInFrustum,
} from '../frustum'
import { sortSplatRecords, SPLAT_STRIDE } from '../tileset'

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

describe('splat record sorting', () => {
  function makeRecords(positions: [number, number, number][]): ArrayBuffer {
    const buf = new ArrayBuffer(positions.length * SPLAT_STRIDE)
    const f32 = new Float32Array(buf)
    const u8 = new Uint8Array(buf)
    positions.forEach((p, i) => {
      f32[i * 8] = p[0]
      f32[i * 8 + 1] = p[1]
      f32[i * 8 + 2] = p[2]
      // tag each record's color with its original index for identity tracking
      u8[i * SPLAT_STRIDE + 24] = i
    })
    return buf
  }

  it('orders records back-to-front along the view direction', () => {
    const buf = makeRecords([
      [0, 0, 10], // nearest along +z view
      [0, 0, 500], // farthest
      [0, 0, 250],
    ])
    const sorted = sortSplatRecords(buf, 0, 0, 1) // view dir +z
    const f32 = new Float32Array(sorted)
    const zs = [f32[2], f32[8 + 2], f32[16 + 2]]
    expect(zs).toEqual([500, 250, 10]) // far first (back-to-front)
  })

  it('preserves full 32-byte records (no field shearing)', () => {
    const buf = makeRecords([
      [3, 0, 1],
      [1, 0, 99],
      [2, 0, 50],
    ])
    const sorted = sortSplatRecords(buf, 0, 0, 1)
    const f32 = new Float32Array(sorted)
    const u8 = new Uint8Array(sorted)
    // record with z=99 was original index 1 — its color tag must travel with it
    expect(f32[2]).toBe(99)
    expect(u8[24]).toBe(1)
    expect(f32[0]).toBe(1) // x of that record
  })

  it('handles single-record and uniform-depth batches', () => {
    const one = sortSplatRecords(makeRecords([[7, 8, 9]]), 0, 0, 1)
    expect(new Float32Array(one)[0]).toBe(7)
    const same = makeRecords([
      [1, 0, 5],
      [2, 0, 5],
      [3, 0, 5],
    ])
    const sorted = new Float32Array(sortSplatRecords(same, 0, 0, 1))
    const xs = [sorted[0], sorted[8], sorted[16]].sort()
    expect(xs).toEqual([1, 2, 3]) // all retained
  })
})
