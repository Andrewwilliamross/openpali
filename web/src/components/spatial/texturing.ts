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
//
// TWO-PHASE GPU PUBLICATION (load-bearing, do not "simplify"): the async
// pipeline must stop at a CPU-side image. MapLibre v5's Context CACHES GL
// state and only re-asserts it when IT changes something; it dirties that
// cache around custom-layer render() calls — but a texture upload running in
// a fetch/decode microtask BETWEEN frames mutates real GL state (texture
// bindings on whatever unit happens to be active) behind the cache's back.
// MapLibre then skips "redundant" rebinds and its terrain-drape pass samples
// a null texture: ground-imagery tiles composite BLANK and are CACHED blank —
// the persistent base-map dropouts under camera motion. Every gl.* call in
// this file therefore happens inside publishPending(), which the splat layer
// invokes from render() inside its state snapshot/restore envelope.

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
  /** composed image awaiting render-time GPU upload (phase 1 → phase 2) */
  pendingImage: ImageBitmap | TexImageSource | null
  /** binding geometry captured at compose time, applied at publish time */
  pendingOrigin: [number, number] | null
  pendingInvSize: [number, number] | null
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
  private currentFrame = 0 // hysteresis: never evict textures in active use

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
    this.currentFrame = Math.max(this.currentFrame, frame)
    const existing = this.entries.get(nodeId)
    if (existing) {
      existing.lastUsedFrame = frame
      return existing.state === 'ready' ? this.bindings.get(nodeId) ?? null : null
    }
    const entry: NodeTexture = {
      state: 'loading', texture: null, lastUsedFrame: frame,
      pendingImage: null, pendingOrigin: null, pendingInvSize: null,
    }
    this.entries.set(nodeId, entry)
    const gen = this.generation
    void this.compose(entry, gen,
      enuMinX, enuMinY, enuMaxX, enuMaxY, originLon, originLat)
    return null
  }

  private async compose(entry: NodeTexture, gen: number,
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

    // PHASE 1 ends here: park the composed image on the entry. NO gl.* calls
    // on this (async) path — see the header comment. transferToImageBitmap
    // detaches synchronously and frees the canvas backing store.
    entry.pendingImage =
      'transferToImageBitmap' in canvas
        ? (canvas as OffscreenCanvas).transferToImageBitmap()
        : (canvas as TexImageSource)
    entry.pendingOrigin = [enuMinX, enuMaxY] // west edge, NORTH edge (v grows south)
    entry.pendingInvSize = [1 / (enuMaxX - enuMinX), 1 / (enuMaxY - enuMinY)]
    this.onReady() // schedules a repaint; publishPending() runs inside render()
  }

  /** How many composed images are waiting for render-time upload. */
  get pendingCount(): number {
    let n = 0
    for (const [, e] of this.entries) if (e.pendingImage) n++
    return n
  }

  /**
   * PHASE 2: upload up to `maxUploads` pending images. MUST be called from the
   * splat layer's render(), inside its GL state envelope. Pixel-store unpack
   * state is set explicitly and restored exactly — texImage2D semantics depend
   * on it and MapLibre's cached values must remain truthful. Returns the number
   * of images still pending (caller schedules another frame when > 0).
   */
  publishPending(maxUploads: number): number {
    const gl = this.gl
    let uploads = 0
    let pending = 0
    let saved: { flipY: boolean; premult: boolean; align: number;
                 rowLen: number; skipPx: number; skipRows: number;
                 pub: WebGLBuffer | null; tex0: WebGLTexture | null } | null = null
    for (const [nodeId, entry] of this.entries) {
      if (!entry.pendingImage) continue
      if (uploads >= maxUploads) {
        pending++
        continue
      }
      if (!saved) {
        saved = {
          flipY: gl.getParameter(gl.UNPACK_FLIP_Y_WEBGL) as boolean,
          premult: gl.getParameter(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL) as boolean,
          align: gl.getParameter(gl.UNPACK_ALIGNMENT) as number,
          rowLen: gl.getParameter(gl.UNPACK_ROW_LENGTH) as number,
          skipPx: gl.getParameter(gl.UNPACK_SKIP_PIXELS) as number,
          skipRows: gl.getParameter(gl.UNPACK_SKIP_ROWS) as number,
          // a bound PBO silently changes texImage2D's data source (WebGL2)
          pub: gl.getParameter(gl.PIXEL_UNPACK_BUFFER_BINDING) as WebGLBuffer | null,
          tex0: gl.getParameter(gl.TEXTURE_BINDING_2D) as WebGLTexture | null,
        }
        gl.bindBuffer(gl.PIXEL_UNPACK_BUFFER, null)
        gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false)
        gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false)
        gl.pixelStorei(gl.UNPACK_ALIGNMENT, 4)
        gl.pixelStorei(gl.UNPACK_ROW_LENGTH, 0)
        gl.pixelStorei(gl.UNPACK_SKIP_PIXELS, 0)
        gl.pixelStorei(gl.UNPACK_SKIP_ROWS, 0)
      }
      const img = entry.pendingImage
      entry.pendingImage = null
      const tex = gl.createTexture()
      if (!tex) {
        entry.state = 'failed'
        if ('close' in img) (img as ImageBitmap).close()
        continue
      }
      gl.bindTexture(gl.TEXTURE_2D, tex)
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE,
        img as TexImageSource)
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR)
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR)
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE)
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE)
      if ('close' in img) (img as ImageBitmap).close()
      entry.texture = tex
      entry.state = 'ready'
      this.bytes += TEX_BYTES
      this.bindings.set(nodeId, {
        texture: tex,
        originEnu: entry.pendingOrigin as [number, number],
        invSizeEnu: entry.pendingInvSize as [number, number],
      })
      entry.pendingOrigin = null
      entry.pendingInvSize = null
      uploads++
    }
    if (saved) {
      gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, saved.flipY)
      gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, saved.premult)
      gl.pixelStorei(gl.UNPACK_ALIGNMENT, saved.align)
      gl.pixelStorei(gl.UNPACK_ROW_LENGTH, saved.rowLen)
      gl.pixelStorei(gl.UNPACK_SKIP_PIXELS, saved.skipPx)
      gl.pixelStorei(gl.UNPACK_SKIP_ROWS, saved.skipRows)
      gl.bindBuffer(gl.PIXEL_UNPACK_BUFFER, saved.pub)
      gl.bindTexture(gl.TEXTURE_2D, saved.tex0)
      this.evictOverBudget() // GL deletes — also render-time only
    }
    return pending
  }

  /** Drop a node's texture (called when the splat node itself is evicted).
   *  Callers run inside the render envelope (eviction is render-time only). */
  evict(nodeId: number): void {
    const e = this.entries.get(nodeId)
    if (!e) return
    if (e.texture) {
      this.gl.deleteTexture(e.texture)
      this.bytes -= TEX_BYTES
    }
    if (e.pendingImage && 'close' in e.pendingImage) (e.pendingImage as ImageBitmap).close()
    this.entries.delete(nodeId)
    this.bindings.delete(nodeId)
  }

  private evictOverBudget(): void {
    if (this.bytes <= MAX_TEX_BYTES) return
    // hysteresis: a texture used in the last ~2s of frames is part of the
    // active working set — evicting it would re-fetch + re-compose next frame
    // (the flicker/churn loop). Only idle textures are reclaimable.
    const ready = [...this.entries.entries()]
      .filter(([, e]) => e.state === 'ready' && e.lastUsedFrame < this.currentFrame - 120)
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
      if (e.pendingImage && 'close' in e.pendingImage) (e.pendingImage as ImageBitmap).close()
    }
    this.entries.clear()
    this.bindings.clear()
    this.bytes = 0
  }
}
