// 3D Tiles 1.1 splat-pyramid loader: tileset parse, node tree, .splat payloads.
//
// All node geometry lives in one local ENU frame (metres, east/north/up) about
// the tileset origin (manifest.origin). Payloads are 32-byte splat records:
//   float32[3] position (ENU m) · float32[3] scale (m) · u8[4] rgba · u8[4] quat

export const SPLAT_STRIDE = 32

export interface TilesetManifest {
  tileset: string
  picking: string
  origin: { lon: number; lat: number; alt_ellipsoidal_m: number }
  geoid_offset_m: number
  splats: number
  parcels: number
  nodes: number
  levels: number
  bytes: number
}

interface RawTile {
  boundingVolume: { box: number[] }
  geometricError: number
  refine?: string
  content?: { uri: string }
  children?: RawTile[]
  transform?: number[]
  extras?: { contentMinZ?: number }
}

export type NodeState = 'unloaded' | 'loading' | 'ready' | 'failed'

export interface SplatNode {
  id: number
  uri: string
  geometricError: number
  // AABB in ENU metres (boxes are axis-aligned by construction in our tiler)
  cx: number
  cy: number
  cz: number
  hx: number
  hy: number
  hz: number
  baseZ: number // ENU z of the node's lowest extent (terrain-clamp anchor)
  children: SplatNode[]
  parent: SplatNode | null
  // runtime state
  state: NodeState
  splatCount: number
  bytes: ArrayBuffer | null // CPU copy retained for depth re-sorting
  slot: import('./BufferPool').PoolSlot | null
  glBuffer: WebGLBuffer | null // dedicated buffer for oversize nodes only
  vao: WebGLVertexArrayObject | null
  firstDrawnAt: number // fade anchor: first frame actually DRAWN (0 = never)
  failedAt: number // performance.now() of last fetch failure (retry cooldown)
  lastUsedFrame: number
  /** ready nodes in this subtree (incl. self) — lets the zoom-out fallback
   *  descend ONLY where resident content exists instead of flood-requesting
   *  the entire tree */
  residentDesc: number
  lastZProbeFrame: number // DEM probe throttle while terrain tiles stream
  zOffset: number // terrain clamp, metres ENU (NaN = not yet computed)
  zOffsetReliable: boolean // false while DEM tiles were still streaming
  /** camera ENU position the node's records were last depth-sorted from.
   *  Radial-distance sort keys are rotation-invariant: only camera
   *  TRANSLATION (relative to node distance) makes an order stale. */
  sortedCamX: number
  sortedCamY: number
  sortedCamZ: number
}

export interface SplatTileset {
  root: SplatNode
  nodes: SplatNode[]
  rootGeometricError: number
  maxLeafBytes: number
}

export function parseTileset(json: {
  geometricError: number
  root: RawTile
}): SplatTileset {
  const nodes: SplatNode[] = []
  let maxLeafBytes = 0

  const build = (raw: RawTile, parent: SplatNode | null): SplatNode => {
    const b = raw.boundingVolume.box
    const node: SplatNode = {
      id: nodes.length,
      uri: raw.content?.uri ?? '',
      geometricError: raw.geometricError,
      cx: b[0],
      cy: b[1],
      cz: b[2],
      hx: Math.abs(b[3]),
      hy: Math.abs(b[7]),
      hz: Math.abs(b[11]),
      // clamp anchor: the CONTENT's lowest point. The octree cube bottom is
      // unrelated to content z (isotropic cubes) — falling back to it produces
      // kilometre-scale offsets on coarse nodes.
      baseZ: raw.extras?.contentMinZ ?? b[2] - Math.abs(b[11]),
      children: [],
      parent,
      state: 'unloaded',
      splatCount: 0,
      bytes: null,
      slot: null,
      glBuffer: null,
      vao: null,
      firstDrawnAt: 0,
      failedAt: 0,
      lastUsedFrame: 0,
      residentDesc: 0,
      lastZProbeFrame: -100,
      zOffset: Number.NaN,
      zOffsetReliable: false,
      sortedCamX: Number.POSITIVE_INFINITY,
      sortedCamY: Number.POSITIVE_INFINITY,
      sortedCamZ: Number.POSITIVE_INFINITY,
    }
    nodes.push(node)
    for (const c of raw.children ?? []) node.children.push(build(c, node))
    return node
  }

  const root = build(json.root, null)
  for (const n of nodes) {
    if (n.children.length === 0) {
      // worst case payload drives the buffer-pool slot size; refined after load
      maxLeafBytes = Math.max(maxLeafBytes, 1)
    }
  }
  return { root, nodes, rootGeometricError: json.geometricError, maxLeafBytes }
}

/** Bounded-concurrency fetcher for node payloads with in-flight dedup. */
export class TileFetcher {
  private baseUrl: string
  private inflight = new Map<number, Promise<ArrayBuffer | null>>()
  private active = 0
  private queue: (() => void)[] = []
  private maxConcurrent: number

  constructor(baseUrl: string, maxConcurrent = 6) {
    this.baseUrl = baseUrl.replace(/\/$/, '')
    this.maxConcurrent = maxConcurrent
  }

  private slotFree(): Promise<void> {
    if (this.active < this.maxConcurrent) {
      this.active++
      return Promise.resolve()
    }
    return new Promise((res) => this.queue.push(() => {
      this.active++
      res()
    }))
  }

  private releaseSlot(): void {
    this.active--
    const next = this.queue.shift()
    if (next) next()
  }

  fetchNode(node: SplatNode): Promise<ArrayBuffer | null> {
    const existing = this.inflight.get(node.id)
    if (existing) return existing
    const p = (async (): Promise<ArrayBuffer | null> => {
      await this.slotFree()
      try {
        const resp = await fetch(`${this.baseUrl}/${node.uri}`)
        if (!resp.ok) return null
        const buf = await resp.arrayBuffer()
        if (buf.byteLength % SPLAT_STRIDE !== 0) return null
        return buf
      } catch {
        return null
      } finally {
        this.releaseSlot()
        this.inflight.delete(node.id)
      }
    })()
    this.inflight.set(node.id, p)
    return p
  }
}

/**
 * In-place back-to-front reorder of a node's CPU splat records by RADIAL
 * distance to the camera position (ENU). Radial keys are rotation-invariant
 * (view-axis projections reorder under pure rotation — StopThePop's popping
 * mechanism — forcing constant re-sorts mid-orbit); distance is monotonic, so
 * back-to-front blending order is preserved. 16-bit counting sort on
 * quantised depth — O(n), no allocation churn beyond two reused scratch
 * buffers.
 */
const scratchKeys = { keys: new Uint16Array(0), counts: new Uint32Array(65536 + 1) }

export function sortSplatRecords(bytes: ArrayBuffer, camX: number, camY: number,
                                 camZ: number): ArrayBuffer {
  const n = bytes.byteLength / SPLAT_STRIDE
  const f32 = new Float32Array(bytes)
  if (scratchKeys.keys.length < n) scratchKeys.keys = new Uint16Array(n)
  const keys = scratchKeys.keys
  const counts = scratchKeys.counts
  counts.fill(0)

  const d2 = (o: number): number => {
    const dx = f32[o] - camX
    const dy = f32[o + 1] - camY
    const dz = f32[o + 2] - camZ
    return dx * dx + dy * dy + dz * dz
  }

  // depth range pass
  let dMin = Infinity
  let dMax = -Infinity
  for (let i = 0; i < n; i++) {
    const d = d2(i * 8) // 32 bytes = 8 floats
    if (d < dMin) dMin = d
    if (d > dMax) dMax = d
  }
  const span = dMax - dMin || 1
  // back-to-front: larger distance (further) must come FIRST, so
  // key = quantised(far→0, near→65535) and counting sort ascending
  for (let i = 0; i < n; i++) {
    const d = d2(i * 8)
    const k = 65535 - Math.min(65535, Math.max(0, Math.floor(((d - dMin) / span) * 65535)))
    keys[i] = k
    counts[k + 1]++
  }
  for (let k = 0; k < 65536; k++) counts[k + 1] += counts[k]

  const src = new Uint32Array(bytes)
  const out = new ArrayBuffer(bytes.byteLength)
  const dst = new Uint32Array(out)
  for (let i = 0; i < n; i++) {
    const at = counts[keys[i]]++
    const so = i * 8
    const do_ = at * 8
    for (let j = 0; j < 8; j++) dst[do_ + j] = src[so + j]
  }
  return out
}
