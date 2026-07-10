import { describe, expect, it, vi } from 'vitest'
import {
  computeTileCover,
  lonLatToTileXY,
  MAX_TEXTURE_COMPOSES,
  MAX_TEXTURE_QUEUE,
  NodeTextureManager,
  textureFade,
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

describe('texture lifecycle controls', () => {
  it('fades an aerial texture in over the requested duration', () => {
    expect(textureFade(1_000, 1_000, 250)).toBe(0)
    expect(textureFade(1_125, 1_000, 250)).toBeCloseTo(0.5, 9)
    expect(textureFade(1_250, 1_000, 250)).toBe(1)
    expect(textureFade(900, 1_000, 250)).toBe(0)
    expect(textureFade(1_000, 1_000, 0)).toBe(1)
  })

  it('bounds queued compose work and cancels it cleanly on teardown', async () => {
    const fetchStub = vi.fn((_url: RequestInfo | URL, init?: RequestInit) =>
      new Promise<Response>((_resolve, reject) => {
        const signal = init?.signal
        if (signal?.aborted) {
          reject(new Error('aborted'))
          return
        }
        signal?.addEventListener('abort', () => reject(new Error('aborted')), { once: true })
      }))
    vi.stubGlobal('fetch', fetchStub)

    const manager = new NodeTextureManager({} as WebGL2RenderingContext, () => {})
    try {
      const limit = MAX_TEXTURE_COMPOSES + MAX_TEXTURE_QUEUE
      for (let nodeId = 0; nodeId < limit + 8; nodeId++) {
        manager.acquire(nodeId, 1, -64, -64, 64, 64, -118.53, 34.04)
      }
      expect(manager.pendingCount).toBe(limit)

      // Eviction removes identity before aborting, so the async continuations
      // cannot later install orphaned GPU textures.
      manager.evict(0)
      manager.destroy()
      await new Promise<void>((resolve) => setTimeout(resolve, 0))
      expect(manager.pendingCount).toBe(0)
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it('restores MapLibre texture state after an async GPU upload', async () => {
    const TEXTURE0 = 0x84c0
    const TEXTURE2 = TEXTURE0 + 2
    const ACTIVE_TEXTURE = 0x84e0
    const TEXTURE_BINDING_2D = 0x8069
    const TEXTURE_2D = 0x0de1
    const previousTexture0 = {} as WebGLTexture
    const previousTexture2 = {} as WebGLTexture
    const uploadedTexture = {} as WebGLTexture
    const bindings = new Map<number, WebGLTexture | null>([
      [TEXTURE0, previousTexture0],
      [TEXTURE2, previousTexture2],
    ])
    let activeTexture = TEXTURE2
    const gl = {
      TEXTURE0,
      TEXTURE_2D,
      ACTIVE_TEXTURE,
      TEXTURE_BINDING_2D,
      RGBA: 0x1908,
      UNSIGNED_BYTE: 0x1401,
      TEXTURE_MIN_FILTER: 0x2801,
      TEXTURE_MAG_FILTER: 0x2800,
      TEXTURE_WRAP_S: 0x2802,
      TEXTURE_WRAP_T: 0x2803,
      LINEAR: 0x2601,
      CLAMP_TO_EDGE: 0x812f,
      getParameter: vi.fn((param: number) =>
        param === ACTIVE_TEXTURE ? activeTexture : bindings.get(activeTexture) ?? null),
      activeTexture: vi.fn((unit: number) => {
        activeTexture = unit
      }),
      createTexture: vi.fn(() => uploadedTexture),
      bindTexture: vi.fn((_target: number, texture: WebGLTexture | null) => {
        bindings.set(activeTexture, texture)
      }),
      texImage2D: vi.fn(),
      texParameteri: vi.fn(),
      deleteTexture: vi.fn(),
    } as unknown as WebGL2RenderingContext
    const drawImage = vi.fn()
    const Canvas = class {
      width: number
      height: number

      constructor(width: number, height: number) {
        this.width = width
        this.height = height
      }

      getContext(type: string) {
        return type === '2d' ? { drawImage } : null
      }
    }
    vi.stubGlobal('OffscreenCanvas', Canvas)
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      blob: async () => ({}) as Blob,
    })))
    vi.stubGlobal('createImageBitmap', vi.fn(async () => ({ close: vi.fn() })))

    let ready!: () => void
    const uploaded = new Promise<void>((resolve) => {
      ready = resolve
    })
    const manager = new NodeTextureManager(gl, ready)
    try {
      manager.acquire(1, 1, -64, -64, 64, 64, -118.53, 34.04)
      await uploaded

      expect(activeTexture).toBe(TEXTURE2)
      expect(bindings.get(TEXTURE0)).toBe(previousTexture0)
      expect(bindings.get(TEXTURE2)).toBe(previousTexture2)
      expect(gl.activeTexture).toHaveBeenLastCalledWith(TEXTURE2)
      expect(gl.bindTexture).toHaveBeenLastCalledWith(TEXTURE_2D, previousTexture0)
    } finally {
      manager.destroy()
      vi.unstubAllGlobals()
    }
  })
})
