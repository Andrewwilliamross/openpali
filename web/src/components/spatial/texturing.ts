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
// happens off the render loop. A small, cancellation-aware queue prevents a
// newly refined cut from issuing hundreds of image requests at once; a node
// draws score-tinted until its texture lands, then the renderer fades it in.

const WAYBACK_RELEASE = 16453
// NOTE: Wayback WMTS path is {z}/{y}/{x} — Y BEFORE X (verified Phase 2).
const WAYBACK_URL = (z: number, x: number, y: number): string =>
  `https://wayback.maptiles.arcgis.com/arcgis/rest/services/world_imagery/wmts/1.0.0/default028mm/mapserver/tile/${WAYBACK_RELEASE}/${z}/${y}/${x}`

export const WAYBACK_TEX_ATTRIBUTION =
  'Imagery: Esri Wayback (pre-fire) — Esri, Vantor, Earthstar Geographics'

const TEX_SIZE = 256
const TEX_BYTES = TEX_SIZE * TEX_SIZE * 4
const MAX_TEX_BYTES = 112 * 1024 * 1024 // ≈448 resident node textures
/** Bound decode/canvas work as well as the service's concurrent tile requests. */
export const MAX_TEXTURE_COMPOSES = 3
/** Queued jobs, in addition to the active compose jobs above. */
export const MAX_TEXTURE_QUEUE = 24
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

type TexState = 'queued' | 'loading' | 'ready' | 'failed'

interface NodeTexture {
  state: TexState
  texture: WebGLTexture | null
  lastUsedFrame: number
  controller: AbortController | null
}

interface TextureRequest {
  nodeId: number
  entry: NodeTexture
  generation: number
  enuMinX: number
  enuMinY: number
  enuMaxX: number
  enuMaxY: number
  originLon: number
  originLat: number
}

export interface TextureBinding {
  texture: WebGLTexture
  /** ENU metres of the texture rectangle: [minX (west), maxY (north)] */
  originEnu: [number, number]
  /** [1/widthM, 1/heightM] */
  invSizeEnu: [number, number]
  /** `performance.now()` when the GPU texture became drawable. */
  readyAt: number
}

/** Clamp a texture's score-tint → aerial-image cross-fade to [0, 1]. */
export function textureFade(now: number, readyAt: number, durationMs: number): number {
  if (durationMs <= 0) return 1
  return Math.min(1, Math.max(0, (now - readyAt) / durationMs))
}

export class NodeTextureManager {
  private gl: WebGL2RenderingContext
  private entries = new Map<number, NodeTexture>()
  private bindings = new Map<number, TextureBinding>()
  private queue: TextureRequest[] = []
  private activeComposes = 0
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

  /** Includes active and queued jobs; useful for lightweight renderer diagnostics. */
  get pendingCount(): number {
    return this.activeComposes + this.queue.length
  }

  /**
   * Texture for a node, or null while loading/unavailable. First call queues
   * a bounded async fetch+compose; the caller re-renders when `onReady` fires.
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
    // Do not let one newly-visible cut allocate unbounded queue entries. Nodes
    // skipped here remain score-tinted and can be reconsidered next frame.
    if (this.pendingCount >= MAX_TEXTURE_COMPOSES + MAX_TEXTURE_QUEUE) return null

    const entry: NodeTexture = {
      state: 'queued',
      texture: null,
      lastUsedFrame: frame,
      controller: null,
    }
    this.entries.set(nodeId, entry)
    this.queue.push({
      nodeId,
      entry,
      generation: this.generation,
      enuMinX,
      enuMinY,
      enuMaxX,
      enuMaxY,
      originLon,
      originLat,
    })
    this.pumpQueue()
    return null
  }

  private isCurrent(nodeId: number, entry: NodeTexture, generation: number): boolean {
    return this.generation === generation && this.entries.get(nodeId) === entry
  }

  private pumpQueue(): void {
    while (this.activeComposes < MAX_TEXTURE_COMPOSES && this.queue.length > 0) {
      const request = this.queue.shift() as TextureRequest
      if (!this.isCurrent(request.nodeId, request.entry, request.generation) ||
          request.entry.state !== 'queued') continue

      request.entry.state = 'loading'
      request.entry.controller = new AbortController()
      this.activeComposes++
      void this.compose(request, request.entry.controller.signal).finally(() => {
        this.activeComposes--
        if (this.entries.get(request.nodeId) === request.entry) {
          request.entry.controller = null
        }
        this.pumpQueue()
      })
    }
  }

  private async compose(request: TextureRequest, signal: AbortSignal): Promise<void> {
    const {
      nodeId,
      entry,
      generation,
      enuMinX,
      enuMinY,
      enuMaxX,
      enuMaxY,
      originLon,
      originLat,
    } = request
    const stillCurrent = (): boolean =>
      this.isCurrent(nodeId, entry, generation) && entry.state === 'loading'
    if (!stillCurrent()) return

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
      if (stillCurrent()) entry.state = 'failed'
      return
    }

    const bitmaps = await Promise.all(cover.tiles.map(async (t) => {
      try {
        const resp = await fetch(WAYBACK_URL(t.z, t.x, t.y), { signal })
        if (!resp.ok) return null
        return await createImageBitmap(await resp.blob())
      } catch {
        return null
      }
    }))
    if (!stillCurrent()) {
      bitmaps.forEach((b) => b?.close())
      return // evicted or reset while fetching
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
      bitmaps.forEach((b) => b?.close())
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

    if (!stillCurrent()) return

    const gl = this.gl
    const tex = gl.createTexture()
    if (!tex) {
      if (stillCurrent()) entry.state = 'failed'
      return
    }
    // This continuation runs outside MapLibre's custom-layer render callback.
    // Upload on a known unit, then restore its previous binding and whichever
    // unit MapLibre had selected so the next map pass inherits no raw GL state.
    const previousActiveTexture = gl.getParameter(gl.ACTIVE_TEXTURE) as number
    gl.activeTexture(gl.TEXTURE0)
    const previousTexture0 = gl.getParameter(gl.TEXTURE_BINDING_2D) as WebGLTexture | null
    try {
      gl.bindTexture(gl.TEXTURE_2D, tex)
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE,
        canvas as TexImageSource)
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR)
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR)
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE)
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE)
    } catch {
      gl.deleteTexture(tex)
      if (stillCurrent()) entry.state = 'failed'
      return
    } finally {
      gl.bindTexture(gl.TEXTURE_2D, previousTexture0)
      gl.activeTexture(previousActiveTexture)
    }

    // `evict()` can run while fetch/decode is in flight. Do not let its old
    // continuation recreate an entry or leak a texture after it was removed.
    if (!stillCurrent()) {
      gl.deleteTexture(tex)
      return
    }

    entry.texture = tex
    entry.state = 'ready'
    this.bytes += TEX_BYTES
    this.bindings.set(nodeId, {
      texture: tex,
      originEnu: [enuMinX, enuMaxY], // west edge, NORTH edge (v grows south)
      invSizeEnu: [1 / (enuMaxX - enuMinX), 1 / (enuMaxY - enuMinY)],
      readyAt: performance.now(),
    })
    this.evictOverBudget()
    this.onReady()
  }

  /** Drop a node's texture (called when the splat node itself is evicted). */
  evict(nodeId: number): void {
    const e = this.entries.get(nodeId)
    if (!e) return
    // Remove identity before aborting: an in-flight continuation must fail its
    // liveness check even if the same node is queued again immediately.
    this.entries.delete(nodeId)
    this.bindings.delete(nodeId)
    if (e.state === 'queued') {
      this.queue = this.queue.filter((request) => request.entry !== e)
    }
    e.controller?.abort()
    if (e.texture) {
      this.gl.deleteTexture(e.texture)
      this.bytes -= TEX_BYTES
    }
    this.pumpQueue()
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
      e.controller?.abort()
      if (e.texture) this.gl.deleteTexture(e.texture)
    }
    this.entries.clear()
    this.bindings.clear()
    this.queue = []
    this.bytes = 0
  }
}
