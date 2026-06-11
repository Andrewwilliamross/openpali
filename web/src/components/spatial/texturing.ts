// Projective aerial texturing for the splat layer.
//
// Per LEAF octree node we compose the Esri Wayback PRE-FIRE orthophoto tiles
// (release 16453 — the last capture before the Jan 2025 fire, the same imagery
// as the detail-card thumbnails) covering the node's footprint into ONE 256px
// texture, mapped to the node's exact mercator rectangle. The fragment shader
// then projects each surfel's ENU position into that rectangle — true
// projective alignment, since the imagery itself is Web-Mercator.
//
// Pre-fire imagery on pre-fire hulls is deliberate: the 3D geometry IS the
// pre-fire building stock; post-fire flights (NOAA) show rubble and cleared
// pads, which would be incoherent projected onto intact volumes.
//
// All tile fetch/decode is async (fetch → createImageBitmap) and composition
// happens off the render loop; a node draws score-tinted until its texture
// lands, then the existing 250 ms fade handles the transition visually.

const WAYBACK_RELEASE = 16453
// NOTE: Wayback WMTS path is {z}/{y}/{x} — Y BEFORE X (verified Phase 2).
const WAYBACK_URL = (z: number, x: number, y: number): string =>
  `https://wayback.maptiles.arcgis.com/arcgis/rest/services/world_imagery/wmts/1.0.0/default028mm/mapserver/tile/${WAYBACK_RELEASE}/${z}/${y}/${x}`

export const WAYBACK_TEX_ATTRIBUTION =
  'Imagery: Esri Wayback (pre-fire) — Esri, Vantor, Earthstar Geographics'

const TEX_SIZE = 256
const TEX_BYTES = TEX_SIZE * TEX_SIZE * 4
const MAX_TEX_BYTES = 112 * 1024 * 1024 // ≈448 resident node textures
const MAX_ZOOM = 19
const MIN_ZOOM = 12
const EQUATOR_M = 40075016.686

// ---------------------------------------------------------------------------
// mercator math (unit-tested)
// ---------------------------------------------------------------------------

/** Fractional Web-Mercator tile coordinates of a lon/lat at zoom z. */
export function lonLatToTileXY(lon: number, lat: number, z: number
                               ): { x: number; y: number } {
  const n = 2 ** z
  const latRad = (lat * Math.PI) / 180
  return {
    x: ((lon + 180) / 360) * n,
    y: ((1 - Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) / 2) * n,
  }
}

/** Zoom level whose tile span best matches a node of `widthM` metres at `lat`
 *  (one composed texture should need at most a 2×2 tile fetch). */
export function zoomForNodeWidth(widthM: number, lat: number): number {
  const cos = Math.cos((lat * Math.PI) / 180)
  // tile ground span at z: EQUATOR·cos(lat)/2^z  — want span ≥ width/1.5
  const z = Math.floor(Math.log2((EQUATOR_M * cos * 1.5) / Math.max(widthM, 1)))
  return Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, z))
}

export interface TileCover {
  zoom: number
  tiles: { z: number; x: number; y: number }[]
  // mercator-unit bbox of the node rectangle (x right, y DOWN/south)
  mx0: number
  my0: number
  mx1: number
  my1: number
}

/** The Wayback tiles covering a lon/lat bbox, plus its mercator rectangle. */
export function computeTileCover(lonMin: number, latMin: number, lonMax: number,
                                 latMax: number, zoom: number): TileCover {
  const n = 2 ** zoom
  const a = lonLatToTileXY(lonMin, latMax, zoom) // NW → smallest x AND y
  const b = lonLatToTileXY(lonMax, latMin, zoom) // SE
  const tx0 = Math.floor(a.x)
  const ty0 = Math.floor(a.y)
  const tx1 = Math.floor(b.x)
  const ty1 = Math.floor(b.y)
  const tiles: { z: number; x: number; y: number }[] = []
  for (let y = ty0; y <= ty1; y++) {
    for (let x = tx0; x <= tx1; x++) {
      if (x >= 0 && y >= 0 && x < n && y < n) tiles.push({ z: zoom, x, y })
    }
  }
  return { zoom, tiles, mx0: a.x / n, my0: a.y / n, mx1: b.x / n, my1: b.y / n }
}

// ---------------------------------------------------------------------------
// per-node texture lifecycle
// ---------------------------------------------------------------------------

type TexState = 'loading' | 'ready' | 'failed'

interface NodeTexture {
  state: TexState
  texture: WebGLTexture | null
  lastUsedFrame: number
}

export interface TextureBinding {
  texture: WebGLTexture
  /** ENU metres of the texture rectangle: [minX (west), maxY (north)] */
  originEnu: [number, number]
  /** [1/widthM, 1/heightM] */
  invSizeEnu: [number, number]
}

export class NodeTextureManager {
  private gl: WebGL2RenderingContext
  private entries = new Map<number, NodeTexture>()
  private bindings = new Map<number, TextureBinding>()
  private bytes = 0
  private generation = 0
  private onReady: () => void

  constructor(gl: WebGL2RenderingContext, onReady: () => void) {
    this.gl = gl
    this.onReady = onReady
  }

  get residentBytes(): number {
    return this.bytes
  }

  /**
   * Texture for a node, or null while loading/unavailable. First call kicks
   * off the async fetch+compose; the caller re-renders when `onReady` fires.
   * Geometry args are the node's ENU bbox + the linearisation origin.
   */
  acquire(nodeId: number, frame: number,
          enuMinX: number, enuMinY: number, enuMaxX: number, enuMaxY: number,
          originLon: number, originLat: number): TextureBinding | null {
    const existing = this.entries.get(nodeId)
    if (existing) {
      existing.lastUsedFrame = frame
      return existing.state === 'ready' ? this.bindings.get(nodeId) ?? null : null
    }
    const entry: NodeTexture = { state: 'loading', texture: null, lastUsedFrame: frame }
    this.entries.set(nodeId, entry)
    const gen = this.generation
    void this.compose(nodeId, entry, gen,
      enuMinX, enuMinY, enuMaxX, enuMaxY, originLon, originLat)
    return null
  }

  private async compose(nodeId: number, entry: NodeTexture, gen: number,
                        enuMinX: number, enuMinY: number, enuMaxX: number,
                        enuMaxY: number, originLon: number, originLat: number,
                        ): Promise<void> {
    // ENU bbox → lon/lat via the same linearisation the render layer uses
    const latRad = (originLat * Math.PI) / 180
    const mPerLon = 111_320 * Math.cos(latRad)
    const mPerLat = 110_574
    const lonMin = originLon + enuMinX / mPerLon
    const lonMax = originLon + enuMaxX / mPerLon
    const latMin = originLat + enuMinY / mPerLat
    const latMax = originLat + enuMaxY / mPerLat

    const zoom = zoomForNodeWidth((enuMaxX - enuMinX) * 1.0, (latMin + latMax) / 2)
    const cover = computeTileCover(lonMin, latMin, lonMax, latMax, zoom)
    if (cover.tiles.length === 0 || cover.tiles.length > 9) {
      entry.state = 'failed'
      return
    }

    let bitmaps: (ImageBitmap | null)[]
    try {
      bitmaps = await Promise.all(cover.tiles.map(async (t) => {
        try {
          const resp = await fetch(WAYBACK_URL(t.z, t.x, t.y))
          if (!resp.ok) return null
          return await createImageBitmap(await resp.blob())
        } catch {
          return null
        }
      }))
    } catch {
      entry.state = 'failed'
      return
    }
    if (gen !== this.generation) {
      bitmaps.forEach((b) => b?.close())
      return // manager was reset while fetching
    }
    if (bitmaps.every((b) => b === null)) {
      entry.state = 'failed'
      return
    }

    // compose the covering tiles onto one canvas mapped to the node's
    // mercator rectangle (canvas y-down == mercator y-down: north is row 0)
    const canvas = typeof OffscreenCanvas !== 'undefined'
      ? new OffscreenCanvas(TEX_SIZE, TEX_SIZE)
      : (() => {
          const c = document.createElement('canvas')
          c.width = TEX_SIZE
          c.height = TEX_SIZE
          return c
        })()
    const ctx = canvas.getContext('2d') as OffscreenCanvasRenderingContext2D | null
    if (!ctx) {
      entry.state = 'failed'
      return
    }
    const n = 2 ** cover.zoom
    const spanX = cover.mx1 - cover.mx0
    const spanY = cover.my1 - cover.my0
    cover.tiles.forEach((t, i) => {
      const bm = bitmaps[i]
      if (!bm) return
      const tileMx = t.x / n
      const tileMy = t.y / n
      const dx = ((tileMx - cover.mx0) / spanX) * TEX_SIZE
      const dy = ((tileMy - cover.my0) / spanY) * TEX_SIZE
      const dw = (1 / n / spanX) * TEX_SIZE
      const dh = (1 / n / spanY) * TEX_SIZE
      ctx.drawImage(bm, dx, dy, dw, dh)
      bm.close()
    })

    const gl = this.gl
    const tex = gl.createTexture()
    if (!tex) {
      entry.state = 'failed'
      return
    }
    gl.bindTexture(gl.TEXTURE_2D, tex)
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE,
      canvas as TexImageSource)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE)
    gl.bindTexture(gl.TEXTURE_2D, null)

    entry.texture = tex
    entry.state = 'ready'
    this.bytes += TEX_BYTES
    this.bindings.set(nodeId, {
      texture: tex,
      originEnu: [enuMinX, enuMaxY], // west edge, NORTH edge (v grows south)
      invSizeEnu: [1 / (enuMaxX - enuMinX), 1 / (enuMaxY - enuMinY)],
    })
    this.evictOverBudget()
    this.onReady()
  }

  /** Drop a node's texture (called when the splat node itself is evicted). */
  evict(nodeId: number): void {
    const e = this.entries.get(nodeId)
    if (!e) return
    if (e.texture) {
      this.gl.deleteTexture(e.texture)
      this.bytes -= TEX_BYTES
    }
    this.entries.delete(nodeId)
    this.bindings.delete(nodeId)
  }

  private evictOverBudget(): void {
    if (this.bytes <= MAX_TEX_BYTES) return
    const ready = [...this.entries.entries()]
      .filter(([, e]) => e.state === 'ready')
      .sort((a, b) => a[1].lastUsedFrame - b[1].lastUsedFrame)
    for (const [id] of ready) {
      if (this.bytes <= MAX_TEX_BYTES * 0.8) break
      this.evict(id)
    }
  }

  destroy(): void {
    this.generation++
    for (const [, e] of this.entries) {
      if (e.texture) this.gl.deleteTexture(e.texture)
    }
    this.entries.clear()
    this.bindings.clear()
    this.bytes = 0
  }
}
