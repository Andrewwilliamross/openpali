import { describe, expect, it } from 'vitest'
import {
  EDGE_BYTES,
  MODE_GHOST,
  MODE_SOLID,
  VERTEX_BYTES,
  creaseEdges,
  edgeInstances,
  octDecode,
  octEncode,
  quantizeV1,
  structureBases,
  structureMode,
  vertexPosition,
  vertexStructure,
} from '../format'

/** A 10 × 10 × 4 m box as float vertices: 8 corners, 12 triangles. */
function box(id: number, x0 = 0, z0 = 100): { vertices: Float32Array; indices: Uint32Array } {
  const corners: [number, number, number][] = []
  for (const z of [z0, z0 + 4]) for (const y of [0, 10]) for (const x of [x0, x0 + 10]) corners.push([x, y, z])
  const vertices = new Float32Array(corners.flatMap(([x, y, z]) => [x, y, z, 0, 0, 1, 0.5, 0.5, id]))
  const quads = [[0, 1, 3, 2], [4, 6, 7, 5], [0, 4, 5, 1], [2, 3, 7, 6], [0, 2, 6, 4], [1, 5, 7, 3]]
  const indices = new Uint32Array(quads.flatMap(([a, b, c, d]) => [a, b, c, a, c, d]))
  return { vertices, indices }
}

describe('octahedral normals', () => {
  it('round-trips unit vectors to within a degree', () => {
    const samples: [number, number, number][] = [
      [0, 0, 1], [0, 0, -1], [1, 0, 0], [0, -1, 0], [0.6, 0, 0.8], [-0.5, 0.5, -0.7071], [0.3, -0.9, 0.3162],
    ]
    for (const [x, y, z] of samples) {
      const len = Math.hypot(x, y, z)
      const [ox, oy] = octEncode(x / len, y / len, z / len)
      expect(Math.abs(ox)).toBeLessThanOrEqual(127)
      const [dx, dy, dz] = octDecode(ox, oy)
      expect((dx * x + dy * y + dz * z) / len).toBeGreaterThan(Math.cos(Math.PI / 180))
    }
  })
})

describe('quantizeV1', () => {
  it('keeps positions within a grid step and preserves structure ids', () => {
    const { vertices } = box(4321, 250.25, 87.5)
    const q = quantizeV1(vertices)
    expect(q.vertexCount).toBe(8)
    expect(q.vertices.byteLength).toBe(8 * VERTEX_BYTES)
    const view = new DataView(q.vertices)
    for (let i = 0; i < 8; i++) {
      const p = vertexPosition(view, i, q.grid)
      for (let a = 0; a < 3; a++) {
        expect(Math.abs(p[a] - vertices[i * 9 + a])).toBeLessThanOrEqual(q.grid.extent[a] / 65535)
      }
      expect(vertexStructure(view, i)).toBe(4321)
    }
  })

  it('does not divide by zero on a flat batch', () => {
    const flat = new Float32Array([0, 0, 5, 0, 0, 1, 0, 0, 1, 10, 0, 5, 0, 0, 1, 1, 0, 1, 0, 10, 5, 0, 0, 1, 0, 1, 1])
    const q = quantizeV1(flat)
    expect(Number.isFinite(vertexPosition(new DataView(q.vertices), 2, q.grid)[2])).toBe(true)
  })
})

describe('creaseEdges', () => {
  it('keeps the 12 edges of a box and drops the 6 face diagonals', () => {
    const { vertices, indices } = box(1)
    const q = quantizeV1(vertices)
    const edges = creaseEdges(q.vertices, indices, q.grid)
    expect(edges.length / 2).toBe(12)
  })

  it('keeps the open boundary of a single flat quad, not its diagonal', () => {
    const quad = new Float32Array([
      0, 0, 0, 0, 0, 1, 0, 0, 7, 10, 0, 0, 0, 0, 1, 1, 0, 7,
      10, 10, 0.5, 0, 0, 1, 1, 1, 7, 0, 10, 0.5, 0, 0, 1, 0, 1, 7,
    ])
    const q = quantizeV1(quad)
    const edges = creaseEdges(q.vertices, new Uint32Array([0, 1, 2, 0, 2, 3]), q.grid)
    expect(edges.length / 2).toBe(4)
  })

  it('welds faces that do not share vertex indices', () => {
    // two coplanar triangles with duplicated vertices along the shared edge
    const soup = new Float32Array([
      0, 0, 0, 0, 0, 1, 0, 0, 2, 10, 0, 0, 0, 0, 1, 0, 0, 2, 10, 10, 1, 0, 0, 1, 0, 0, 2,
      0, 0, 0, 0, 0, 1, 0, 0, 2, 10, 10, 1, 0, 0, 1, 0, 0, 2, 0, 10, 1, 0, 0, 1, 0, 0, 2,
    ])
    const q = quantizeV1(soup)
    const edges = creaseEdges(q.vertices, new Uint32Array([0, 1, 2, 3, 4, 5]), q.grid)
    expect(edges.length / 2).toBe(4) // outline only: the shared diagonal is interior and flat
  })
})

describe('edgeInstances', () => {
  it('packs both endpoints and the structure id per edge', () => {
    const { vertices, indices } = box(9)
    const q = quantizeV1(vertices)
    const edges = creaseEdges(q.vertices, indices, q.grid)
    const packed = new Uint16Array(edgeInstances(q.vertices, edges))
    expect(packed.byteLength).toBe((edges.length / 2) * EDGE_BYTES)
    const source = new Uint16Array(q.vertices)
    for (let e = 0; e < edges.length / 2; e++) {
      expect([...packed.subarray(e * 8, e * 8 + 3)]).toEqual([...source.subarray(edges[e * 2] * 8, edges[e * 2] * 8 + 3)])
      expect([...packed.subarray(e * 8 + 3, e * 8 + 6)]).toEqual([...source.subarray(edges[e * 2 + 1] * 8, edges[e * 2 + 1] * 8 + 3)])
      expect(packed[e * 8 + 6]).toBe(9)
    }
  })
})

describe('structureBases', () => {
  it('reports the lowest vertex of each structure', () => {
    const a = box(1, 0, 100)
    const b = box(2, 50, 140)
    const both = new Float32Array([...a.vertices, ...b.vertices])
    const q = quantizeV1(both)
    const bases = structureBases(q.vertices, q.grid)
    const byId = new Map<number, number>()
    for (let i = 0; i < bases.length; i += 2) byId.set(bases[i], bases[i + 1])
    expect(byId.get(1)).toBeCloseTo(100, 2)
    expect(byId.get(2)).toBeCloseTo(140, 2)
  })
})

describe('structureMode', () => {
  it('ghosts destroyed structures and keeps standing ones solid', () => {
    expect(structureMode('Destroyed (>50%)', true)).toBe(MODE_GHOST)
    expect(structureMode('Destroyed (>50%)', false)).toBe(MODE_GHOST)
    expect(structureMode('No Damage', true)).toBe(MODE_SOLID) // a surviving structure on a burned lot
    expect(structureMode('Major (26-50%)', true)).toBe(MODE_SOLID)
  })

  it('lets the parcel decide when the structure was not inspected', () => {
    expect(structureMode('', true)).toBe(MODE_GHOST)
    expect(structureMode('', false)).toBe(MODE_SOLID)
  })
})
