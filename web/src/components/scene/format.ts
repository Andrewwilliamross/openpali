// Building-scene formats and the pure geometry transforms shared by the worker,
// the render layer and the tests. No DOM or GL here.
//
// GPU vertex (16 bytes), identical for every source format:
//   u16 x, y, z   position on the batch's own grid (see `QuantizedGrid`)
//   i8  ox, oy    octahedral-encoded unit normal
//   u16 id        structure id (0 = no structure; never drawn)
//   u16 u, v      top-down aerial texture coordinate
//   u16 pad
// A batch spans at most a few kilometres, so 16 bits is ≤ 5 cm horizontally
// and ≤ 1 cm vertically.

export const VERTEX_BYTES = 16

/** Scene manifest, as written by `pipeline/openpali/scene` (v2) or by the
 *  2026-09-29 research prototype (v1, float vertices). */
export interface SceneManifest {
  schema: 'openpali-regional-mesh-v1' | 'openpali-scene-v2'
  /** [x, y] of the local origin in MapLibre mercator units (0..1) */
  mercator_origin: [number, number]
  /** mercator units per metre at the origin latitude */
  mercator_metre_scale: number
  nodes: SceneNode[]
  structures: SceneStructure[]
  /** v2: directory of the batch buffers, relative to the manifest */
  buffers?: string
  /** v2: terrain tiles baked where the lidar improves on the regional source */
  terrain?: {
    tiles: string
    minzoom: number
    maxzoom: number
    /** zoom → [x, y] of every baked tile */
    index: Record<string, [number, number][]>
    fallback: string
    fallback_maxzoom: number
  } | null
}

export interface SceneNode {
  id: number
  vertex_count: number
  index_count: number
  /** [west, south, east, north] */
  bounds: [number, number, number, number]
  vertex_bytes: number
  index_bytes: number
  /** v2: width of the stored triangle indices (v1 is always u32) */
  index_type?: 'u16' | 'u32'
  /** aerial tile rectangle the batch's uv spans */
  atlas: { z: number; x: number; y: number; width: number; height: number }
  /** v2 only: position grid, local metres */
  grid?: QuantizedGrid
}

export interface SceneStructure {
  gpu_id: number
  apn: string
  /** county damage inspection class for this structure ('' = not inspected) */
  damage: string
  center: [number, number]
  /** v2 only: lowest footprint elevation, metres NAVD88 */
  base_m?: number
  /** v2 only: metres to add so the flat base sits on the lowest ground under
   *  the footprint, measured at build time */
  ground_delta_m?: number
  /** v2 only: terrain elevation at `center` when `ground_delta_m` was baked */
  ground_m?: number
}

/** position = min + q / 65535 × extent, per axis, in local metres
 *  (x east, y SOUTH, z up: the scene's mercator-aligned frame). */
export interface QuantizedGrid {
  min: [number, number, number]
  extent: [number, number, number]
}

export interface DecodedBatch {
  id: number
  grid: QuantizedGrid
  vertices: ArrayBuffer
  vertexCount: number
  /** triangle list */
  indices: Uint32Array
  /** silhouette and crease edges as `EDGE_BYTES` instances (see `edgeInstances`) */
  edges: ArrayBuffer
  edgeCount: number
  /** [structure id, lowest vertex z] pairs, for sources without a baked base */
  bases: Float32Array
}

// ---------------------------------------------------------------- normals

/** Unit vector → octahedral i8 pair. */
export function octEncode(x: number, y: number, z: number): [number, number] {
  const l1 = Math.abs(x) + Math.abs(y) + Math.abs(z) || 1
  let ox = x / l1
  let oy = y / l1
  if (z < 0) {
    const fx = (1 - Math.abs(oy)) * (ox >= 0 ? 1 : -1)
    const fy = (1 - Math.abs(ox)) * (oy >= 0 ? 1 : -1)
    ox = fx
    oy = fy
  }
  return [Math.round(ox * 127), Math.round(oy * 127)]
}

/** Inverse of `octEncode` (mirrors the vertex shader). */
export function octDecode(ox: number, oy: number): [number, number, number] {
  let x = ox / 127
  let y = oy / 127
  const z = 1 - Math.abs(x) - Math.abs(y)
  if (z < 0) {
    const fx = (1 - Math.abs(y)) * (x >= 0 ? 1 : -1)
    const fy = (1 - Math.abs(x)) * (y >= 0 ? 1 : -1)
    x = fx
    y = fy
  }
  const len = Math.hypot(x, y, z) || 1
  return [x / len, y / len, z / len]
}

// ------------------------------------------------------------ quantization

const FLOATS_V1 = 9 // x, y, z, nx, ny, nz, u, v, id

/** Research-prototype float vertices → the 16-byte GPU layout. */
export function quantizeV1(source: Float32Array): {
  vertices: ArrayBuffer
  vertexCount: number
  grid: QuantizedGrid
} {
  const n = Math.floor(source.length / FLOATS_V1)
  const min: [number, number, number] = [Infinity, Infinity, Infinity]
  const max: [number, number, number] = [-Infinity, -Infinity, -Infinity]
  for (let i = 0; i < n; i++) {
    for (let a = 0; a < 3; a++) {
      const v = source[i * FLOATS_V1 + a]
      if (v < min[a]) min[a] = v
      if (v > max[a]) max[a] = v
    }
  }
  const extent: [number, number, number] = [0, 1, 2].map((a) =>
    Math.max(max[a] - min[a], 1e-3)) as [number, number, number]
  const vertices = new ArrayBuffer(n * VERTEX_BYTES)
  const view = new DataView(vertices)
  for (let i = 0; i < n; i++) {
    const s = i * FLOATS_V1
    const o = i * VERTEX_BYTES
    for (let a = 0; a < 3; a++) {
      view.setUint16(o + a * 2, Math.round(((source[s + a] - min[a]) / extent[a]) * 65535), true)
    }
    const [ox, oy] = octEncode(source[s + 3], source[s + 4], source[s + 5])
    view.setInt8(o + 6, ox)
    view.setInt8(o + 7, oy)
    view.setUint16(o + 8, Math.round(source[s + 8]), true)
    view.setUint16(o + 10, Math.round(clamp01(source[s + 6]) * 65535), true)
    view.setUint16(o + 12, Math.round(clamp01(source[s + 7]) * 65535), true)
  }
  return { vertices, vertexCount: n, grid: { min, extent } }
}

function clamp01(v: number): number {
  return v < 0 ? 0 : v > 1 ? 1 : v
}

/** Position of vertex `i` in local metres. */
export function vertexPosition(view: DataView, i: number, grid: QuantizedGrid,
                               ): [number, number, number] {
  const o = i * VERTEX_BYTES
  return [
    grid.min[0] + (view.getUint16(o, true) / 65535) * grid.extent[0],
    grid.min[1] + (view.getUint16(o + 2, true) / 65535) * grid.extent[1],
    grid.min[2] + (view.getUint16(o + 4, true) / 65535) * grid.extent[2],
  ]
}

export function vertexStructure(view: DataView, i: number): number {
  return view.getUint16(i * VERTEX_BYTES + 8, true)
}

// ------------------------------------------------------------------- edges

/**
 * The edges worth drawing: open boundaries, and creases where two faces meet
 * at more than `creaseDeg`. Drawing every triangle edge would fill flat walls
 * and roofs with their triangulation diagonals.
 *
 * Vertices are welded by quantized position, so faces that do not share
 * vertex indices (normals are per face in the source) still meet at an edge.
 */
export function creaseEdges(vertices: ArrayBuffer, indices: Uint32Array,
                            grid: QuantizedGrid, creaseDeg = 28): Uint32Array {
  const view = new DataView(vertices)
  const weld = new Map<string, number>()
  const welded = new Uint32Array(vertices.byteLength / VERTEX_BYTES)
  for (let i = 0; i < welded.length; i++) {
    const o = i * VERTEX_BYTES
    const key = `${view.getUint16(o, true)},${view.getUint16(o + 2, true)},${view.getUint16(o + 4, true)}`
    let w = weld.get(key)
    if (w === undefined) {
      w = i
      weld.set(key, w)
    }
    welded[i] = w
  }

  const triangles = indices.length / 3
  const normals = new Float32Array(triangles * 3)
  for (let t = 0; t < triangles; t++) {
    const a = vertexPosition(view, indices[t * 3], grid)
    const b = vertexPosition(view, indices[t * 3 + 1], grid)
    const c = vertexPosition(view, indices[t * 3 + 2], grid)
    const ux = b[0] - a[0], uy = b[1] - a[1], uz = b[2] - a[2]
    const vx = c[0] - a[0], vy = c[1] - a[1], vz = c[2] - a[2]
    const nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx
    const len = Math.hypot(nx, ny, nz)
    if (len > 0) {
      normals[t * 3] = nx / len
      normals[t * 3 + 1] = ny / len
      normals[t * 3 + 2] = nz / len
    }
  }

  // edge → [first triangle, original a, original b, keep?]
  const cosCrease = Math.cos((creaseDeg * Math.PI) / 180)
  const edges = new Map<number, { t: number; a: number; b: number; faces: number; sharp: boolean }>()
  const count = welded.length
  for (let t = 0; t < triangles; t++) {
    if (normals[t * 3] === 0 && normals[t * 3 + 1] === 0 && normals[t * 3 + 2] === 0) continue
    for (let e = 0; e < 3; e++) {
      const a = indices[t * 3 + e]
      const b = indices[t * 3 + ((e + 1) % 3)]
      const wa = welded[a]
      const wb = welded[b]
      if (wa === wb) continue
      const key = wa < wb ? wa * count + wb : wb * count + wa
      const seen = edges.get(key)
      if (!seen) {
        edges.set(key, { t, a, b, faces: 1, sharp: false })
        continue
      }
      seen.faces++
      const dot = normals[t * 3] * normals[seen.t * 3]
        + normals[t * 3 + 1] * normals[seen.t * 3 + 1]
        + normals[t * 3 + 2] * normals[seen.t * 3 + 2]
      // abs(): the source's winding is not consistent, so a folded-back face
      // pair must not read as a crease
      if (Math.abs(dot) < cosCrease) seen.sharp = true
    }
  }
  const out: number[] = []
  for (const edge of edges.values()) {
    if (edge.faces === 1 || edge.sharp) out.push(edge.a, edge.b)
  }
  return Uint32Array.from(out)
}

export const EDGE_BYTES = 16

/**
 * Edge instances for screen-space line quads: both endpoints' grid positions
 * and the structure id, 16 bytes each (u16 ax, ay, az, bx, by, bz, id, pad).
 * GL lines are one device pixel wide and unfiltered; a quad per edge gives a
 * chosen width and antialiasing in a single draw.
 */
export function edgeInstances(vertices: ArrayBuffer, edges: Uint32Array): ArrayBuffer {
  const source = new Uint16Array(vertices)
  const perVertex = VERTEX_BYTES / 2
  const count = edges.length / 2
  const out = new Uint16Array(count * (EDGE_BYTES / 2))
  for (let e = 0; e < count; e++) {
    const a = edges[e * 2] * perVertex
    const b = edges[e * 2 + 1] * perVertex
    const o = e * 8
    out[o] = source[a]
    out[o + 1] = source[a + 1]
    out[o + 2] = source[a + 2]
    out[o + 3] = source[b]
    out[o + 4] = source[b + 1]
    out[o + 5] = source[b + 2]
    out[o + 6] = source[a + 4] // structure id lives at byte 8
  }
  return out.buffer
}

/** Lowest vertex per structure, as [id, z] pairs. */
export function structureBases(vertices: ArrayBuffer, grid: QuantizedGrid): Float32Array {
  const view = new DataView(vertices)
  const lowest = new Map<number, number>()
  const n = vertices.byteLength / VERTEX_BYTES
  for (let i = 0; i < n; i++) {
    const id = vertexStructure(view, i)
    const z = grid.min[2] + (view.getUint16(i * VERTEX_BYTES + 4, true) / 65535) * grid.extent[2]
    const seen = lowest.get(id)
    if (seen === undefined || z < seen) lowest.set(id, z)
  }
  const out = new Float32Array(lowest.size * 2)
  let o = 0
  for (const [id, z] of lowest) {
    out[o++] = id
    out[o++] = z
  }
  return out
}

// --------------------------------------------------------- structure state

export const MODE_HIDDEN = 0
export const MODE_SOLID = 1
export const MODE_GHOST = 2
export const FLAG_SELECTED = 4

/** County inspection classes that mean the structure no longer stands. */
const DESTROYED = /^destroyed/i

/**
 * How one structure is drawn. A destroyed structure is a ghost in its
 * parcel's score colour; a standing one is solid. Where the county did not
 * inspect the structure, the parcel's own assessment decides.
 */
export function structureMode(structureDamage: string, parcelDestroyed: boolean): number {
  if (DESTROYED.test(structureDamage)) return MODE_GHOST
  if (structureDamage === '' && parcelDestroyed) return MODE_GHOST
  return MODE_SOLID
}
