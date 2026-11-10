import { describe, expect, it } from 'vitest'
import {
  computeTileCover,
  lonLatToTileXY,
  NodeTextureManager,
  zoomForNodeWidth,
} from '../texturing'

describe('mercator tile math', () => {
  it('matches the live-verified Wayback reference tile', () => {
    // Phase 2 research curl-verified this exact tile at the Palisades point:
    // lon -118.526, lat 34.045 → z18 x=44764, y=104678
    const t = lonLatToTileXY(-118.526, 34.045, 18)
    expect(Math.floor(t.x)).toBe(44764)
    expect(Math.floor(t.y)).toBe(104678)
  })

  it('tile y grows southward', () => {
    const north = lonLatToTileXY(-118.5, 34.1, 15)
    const south = lonLatToTileXY(-118.5, 34.0, 15)
    expect(south.y).toBeGreaterThan(north.y)
  })

  it('zoom shrinks for wider nodes and clamps to the service range', () => {
    const z127 = zoomForNodeWidth(127, 34.04)
    const z500 = zoomForNodeWidth(500, 34.04)
    const z8000 = zoomForNodeWidth(8000, 34.04)
    expect(z127).toBeGreaterThan(z500)
    expect(z500).toBeGreaterThan(z8000)
    expect(z127).toBeLessThanOrEqual(19)
    expect(zoomForNodeWidth(0.5, 34.04)).toBeLessThanOrEqual(19) // clamp high
    expect(zoomForNodeWidth(10_000_000, 34.04)).toBeGreaterThanOrEqual(12) // clamp low
  })
})

describe('tile cover', () => {
  it('a 127 m leaf node needs at most a 2×2 cover at its chosen zoom', () => {
    const lat = 34.0415
    const lon = -118.5285
    const halfDeg = 63.75 / 111_320 / Math.cos((lat * Math.PI) / 180)
    const halfLat = 63.75 / 110_574
    const zoom = zoomForNodeWidth(127.5, lat)
    const cover = computeTileCover(lon - halfDeg, lat - halfLat,
                                   lon + halfDeg, lat + halfLat, zoom)
    expect(cover.tiles.length).toBeGreaterThanOrEqual(1)
    expect(cover.tiles.length).toBeLessThanOrEqual(4)
  })

  it('mercator bbox is ordered and tight around the tiles', () => {
    const cover = computeTileCover(-118.53, 34.04, -118.526, 34.043, 17)
    expect(cover.mx1).toBeGreaterThan(cover.mx0)
    expect(cover.my1).toBeGreaterThan(cover.my0) // y down: south > north
    const n = 2 ** 17
    for (const t of cover.tiles) {
      // every cover tile must intersect the bbox
      expect(t.x / n).toBeLessThanOrEqual(cover.mx1)
      expect((t.x + 1) / n).toBeGreaterThanOrEqual(cover.mx0)
      expect(t.y / n).toBeLessThanOrEqual(cover.my1)
      expect((t.y + 1) / n).toBeGreaterThanOrEqual(cover.my0)
    }
  })

  it('a point-sized bbox still yields exactly one tile', () => {
    const cover = computeTileCover(-118.5285, 34.0415, -118.5285, 34.0415, 18)
    expect(cover.tiles.length).toBe(1)
  })
})

// ---------------------------------------------------------------------------
// two-phase GPU publication (async compose must NEVER touch GL; publishPending
// uploads inside the render envelope and leaves pixel-store state untouched)
// ---------------------------------------------------------------------------

const GLC = {
  TEXTURE_2D: 1, RGBA: 2, UNSIGNED_BYTE: 3, LINEAR: 4, CLAMP_TO_EDGE: 5,
  TEXTURE_MIN_FILTER: 6, TEXTURE_MAG_FILTER: 7, TEXTURE_WRAP_S: 8,
  TEXTURE_WRAP_T: 9, UNPACK_FLIP_Y_WEBGL: 10, UNPACK_PREMULTIPLY_ALPHA_WEBGL: 11,
  UNPACK_ALIGNMENT: 12, UNPACK_ROW_LENGTH: 13, UNPACK_SKIP_PIXELS: 14,
  UNPACK_SKIP_ROWS: 15, PIXEL_UNPACK_BUFFER: 16, PIXEL_UNPACK_BUFFER_BINDING: 17,
  TEXTURE_BINDING_2D: 18,
}

interface FakeGL {
  log: string[]
  pixelStore: Map<number, unknown>
}

function fakeGL(): WebGL2RenderingContext & FakeGL {
  const prevTex = { id: 'maplibre-tex' }
  const prevPbo = { id: 'maplibre-pbo' }
  // MapLibre-style "dirty" ambient state the manager must save and restore
  const pixelStore = new Map<number, unknown>([
    [GLC.UNPACK_FLIP_Y_WEBGL, true],
    [GLC.UNPACK_PREMULTIPLY_ALPHA_WEBGL, true],
    [GLC.UNPACK_ALIGNMENT, 1],
    [GLC.UNPACK_ROW_LENGTH, 7],
    [GLC.UNPACK_SKIP_PIXELS, 3],
    [GLC.UNPACK_SKIP_ROWS, 2],
  ])
  const log: string[] = []
  let texN = 0
  const gl = {
    ...GLC,
    log,
    pixelStore,
    getParameter(p: number) {
      if (p === GLC.TEXTURE_BINDING_2D) return prevTex
      if (p === GLC.PIXEL_UNPACK_BUFFER_BINDING) return prevPbo
      return pixelStore.get(p)
    },
    pixelStorei(p: number, v: unknown) {
      pixelStore.set(p, v)
      log.push(`pixelStorei(${p},${String(v)})`)
    },
    bindBuffer(target: number, b: { id?: string } | null) {
      log.push(`bindBuffer(${target},${b ? b.id : 'null'})`)
    },
    createTexture() {
      texN++
      return { id: `tex${texN}` }
    },
    deleteTexture(t: { id?: string }) {
      log.push(`deleteTexture(${t.id})`)
    },
    bindTexture(_t: number, tex: { id?: string } | null) {
      log.push(`bindTexture(${tex ? tex.id : 'null'})`)
    },
    texImage2D() {
      log.push('texImage2D')
    },
    texParameteri() {
      /* not state we track */
    },
  }
  return gl as unknown as WebGL2RenderingContext & FakeGL
}

function seedPending(tm: NodeTextureManager, nodeId: number,
                     closed: { v: boolean }): void {
  const entries = (tm as unknown as { entries: Map<number, Record<string, unknown>> }).entries
  entries.set(nodeId, {
    state: 'loading', texture: null, lastUsedFrame: 0,
    pendingImage: { close: () => { closed.v = true } },
    pendingOrigin: [-10, 20], pendingInvSize: [0.1, 0.05],
  })
}

describe('NodeTextureManager two-phase publication', () => {
  it('publishPending respects the budget and reports the remainder', () => {
    const gl = fakeGL()
    const tm = new NodeTextureManager(gl, () => {})
    const c1 = { v: false }
    const c2 = { v: false }
    seedPending(tm, 1, c1)
    seedPending(tm, 2, c2)
    expect(tm.pendingCount).toBe(2)
    expect(tm.publishPending(1)).toBe(1) // one uploaded, one still pending
    expect(tm.pendingCount).toBe(1)
    expect(tm.publishPending(8)).toBe(0)
    expect(tm.pendingCount).toBe(0)
    expect(c1.v && c2.v).toBe(true) // bitmaps closed after upload
    // ready entries now resolve through the public acquire() path
    const b = tm.acquire(1, 10, 0, 0, 0, 0, 0, 0)
    expect(b?.originEnu).toEqual([-10, 20])
    expect(b?.invSizeEnu).toEqual([0.1, 0.05])
  })

  it('restores every pixel-store flag, the PBO binding, and the texture binding', () => {
    const gl = fakeGL()
    const tm = new NodeTextureManager(gl, () => {})
    seedPending(tm, 1, { v: false })
    tm.publishPending(4)
    // ambient unpack state must be EXACTLY what MapLibre left there
    expect(gl.pixelStore.get(GLC.UNPACK_FLIP_Y_WEBGL)).toBe(true)
    expect(gl.pixelStore.get(GLC.UNPACK_PREMULTIPLY_ALPHA_WEBGL)).toBe(true)
    expect(gl.pixelStore.get(GLC.UNPACK_ALIGNMENT)).toBe(1)
    expect(gl.pixelStore.get(GLC.UNPACK_ROW_LENGTH)).toBe(7)
    expect(gl.pixelStore.get(GLC.UNPACK_SKIP_PIXELS)).toBe(3)
    expect(gl.pixelStore.get(GLC.UNPACK_SKIP_ROWS)).toBe(2)
    const log = gl.log
    // PBO: unbound for the upload, restored after
    expect(log).toContain(`bindBuffer(${GLC.PIXEL_UNPACK_BUFFER},null)`)
    expect(log[log.length - 2]).toBe(`bindBuffer(${GLC.PIXEL_UNPACK_BUFFER},maplibre-pbo)`)
    // final texture binding back to MapLibre's
    expect(log[log.length - 1]).toBe('bindTexture(maplibre-tex)')
  })

  it('publishing nothing performs zero GL calls', () => {
    const gl = fakeGL()
    const tm = new NodeTextureManager(gl, () => {})
    expect(tm.publishPending(4)).toBe(0)
    expect(gl.log.length).toBe(0)
  })

  it('evicting a pending entry closes its bitmap without GL uploads', () => {
    const gl = fakeGL()
    const tm = new NodeTextureManager(gl, () => {})
    const closed = { v: false }
    seedPending(tm, 7, closed)
    tm.evict(7)
    expect(closed.v).toBe(true)
    expect(tm.pendingCount).toBe(0)
    expect(gl.log.filter((l) => l === 'texImage2D').length).toBe(0)
  })
})
