// MapLibre custom 3D layer streaming the multi-resolution splat pyramid.
//
// Shares MapLibre's WebGL2 context and depth buffer: with terrain enabled the
// terrain pass writes depth (LEQUAL/ReadWrite) before translucent custom
// layers run, so splats depth-test against the live DEM skin. We keep depth
// TEST on and turn depth WRITES off for the blended pass (state restored
// after every render call).
//
// Streaming is screen-space-error driven (3D-Tiles style), not zoom driven:
// each frame the octree is traversed; a node refines into its children only
// when its SSE exceeds threshold AND all children are GPU-resident (REPLACE
// semantics — no holes, no double-draw). GPU memory flows through a fixed
// ring of pre-allocated buffer slots (BufferPool) and an LRU eviction pass.

import type {
  CustomLayerInterface,
  CustomRenderMethodInput,
  Map as MLMap,
} from 'maplibre-gl'
import maplibregl from 'maplibre-gl'
import { BufferPool } from './BufferPool'
import {
  extractFrustumPlanes,
  pointToBoxDistance,
  screenSpaceError,
  sphereInFrustum,
} from './frustum'
import { composeTRS, invert, transformPoint, type Mat4 } from './mat4'
import { compileProgram, SPLAT_FRAG, SPLAT_VERT } from './shaders'
import {
  parseTileset,
  sortSplatRecords,
  SPLAT_STRIDE,
  TileFetcher,
  type SplatNode,
  type SplatTileset,
  type TilesetManifest,
} from './tileset'
import type { SpatialIntersector } from './spatial_intersector'

const SSE_THRESHOLD_PX = 14
const FADE_MS = 250
const SLOT_BYTES = 14000 * SPLAT_STRIDE // matches pipeline leaf_max
const RESIDENT_BYTE_CAP = 144 * 1024 * 1024
const RESORT_DOT_THRESHOLD = 0.995 // ~5.7° view swing triggers a node re-sort
const METERS_PER_DEG_LAT = 110_574
const METERS_PER_DEG_LON_EQ = 111_320 // × cos(lat) for longitude

export class SplatRenderLayer implements CustomLayerInterface {
  readonly id: string
  readonly type = 'custom' as const
  readonly renderingMode = '3d' as const

  private map: MLMap | null = null
  private gl: WebGL2RenderingContext | null = null
  private program: WebGLProgram | null = null
  private uniforms: Record<string, WebGLUniformLocation | null> = {}
  private pool: BufferPool | null = null
  private fetcher: TileFetcher
  private tileset: SplatTileset | null = null
  private manifest: TilesetManifest | null = null
  private baseUrl: string
  private frame = 0
  private residentBytes = 0
  private oversize = new Set<WebGLBuffer>()
  private originMerc: { x: number; y: number; z: number } | null = null
  private metersToMerc = 0
  private matrixF32 = new Float32Array(16)
  private enabled = true
  // bumped on add/remove: in-flight fetch continuations from a previous layer
  // lifetime must not resurrect nodes into the new pool (React StrictMode
  // double-mounts custom layers)
  private generation = 0
  private onTerrainChange = (): void => {
    if (!this.tileset) return
    for (const n of this.tileset.nodes) {
      n.zOffset = Number.NaN
      n.zOffsetReliable = false
    }
    this.map?.triggerRepaint()
  }

  private intersector: SpatialIntersector | null = null

  constructor(id: string, baseUrl: string, intersector?: SpatialIntersector) {
    this.id = id
    this.baseUrl = baseUrl.replace(/\/$/, '')
    this.fetcher = new TileFetcher(this.baseUrl)
    this.intersector = intersector ?? null
  }

  setEnabled(on: boolean): void {
    this.enabled = on
    this.map?.triggerRepaint()
  }

  // ------------------------------------------------------------------ setup

  onAdd(map: MLMap, gl: WebGLRenderingContext | WebGL2RenderingContext): void {
    if (!(gl instanceof WebGL2RenderingContext)) {
      throw new Error('SplatRenderLayer requires a WebGL2 context')
    }
    this.map = map
    this.gl = gl
    this.generation++
    this.program = compileProgram(gl, SPLAT_VERT, SPLAT_FRAG)
    for (const name of ['u_matrix', 'u_viewport', 'u_fade', 'u_zOffset']) {
      this.uniforms[name] = gl.getUniformLocation(this.program, name)
    }
    this.pool = new BufferPool(gl, SLOT_BYTES, 48, 16)
    map.on('terrain', this.onTerrainChange)

    void (async () => {
      try {
        const mResp = await fetch(`${this.baseUrl}/manifest.json`)
        if (!mResp.ok) return
        const manifest = (await mResp.json()) as TilesetManifest
        const tResp = await fetch(`${this.baseUrl}/${manifest.tileset}`)
        if (!tResp.ok) return
        this.manifest = manifest
        this.tileset = parseTileset(await tResp.json())
        const oLngLat: [number, number] = [manifest.origin.lon, manifest.origin.lat]
        // render datum: AMSL = ellipsoidal − geoid offset (offset is negative in LA)
        const altAMSL = manifest.origin.alt_ellipsoidal_m - manifest.geoid_offset_m
        const mc = maplibregl.MercatorCoordinate.fromLngLat(oLngLat, altAMSL)
        this.originMerc = { x: mc.x, y: mc.y, z: mc.z ?? 0 }
        this.metersToMerc = mc.meterInMercatorCoordinateUnits()
        map.triggerRepaint()
      } catch {
        /* manifest absent — layer stays dormant */
      }
    })()
  }

  onRemove(map: MLMap, gl: WebGLRenderingContext | WebGL2RenderingContext): void {
    map.off('terrain', this.onTerrainChange)
    this.generation++ // in-flight fetch continuations become no-ops
    const gl2 = gl as WebGL2RenderingContext
    if (this.tileset) {
      for (const n of this.tileset.nodes) this.evictNode(n)
    }
    for (const b of this.oversize) gl2.deleteBuffer(b)
    this.oversize.clear()
    this.pool?.destroy()
    if (this.program) gl2.deleteProgram(this.program)
    this.program = null
    this.pool = null
    this.map = null
    this.gl = null
    this.tileset = null
    this.residentBytes = 0
  }

  // ------------------------------------------------------------- gpu loading

  private originAltAMSL(): number {
    const m = this.manifest
    if (!m) return 0
    return m.origin.alt_ellipsoidal_m - m.geoid_offset_m
  }

  private static readonly FAIL_RETRY_MS = 15_000

  private requestLoad(node: SplatNode, viewDir: [number, number, number]): void {
    if (!node.uri) return
    // failed fetches retry after a cooldown — a transient network error must
    // not freeze the subtree at coarse LOD for the whole session
    if (node.state === 'failed' &&
        performance.now() - node.failedAt > SplatRenderLayer.FAIL_RETRY_MS) {
      node.state = 'unloaded'
    }
    if (node.state !== 'unloaded') return
    node.state = 'loading'
    const gen = this.generation
    void this.fetcher.fetchNode(node).then((buf) => {
      if (gen !== this.generation) return // layer was removed/re-added meanwhile
      if (!buf || !this.gl || !this.pool) {
        node.state = buf ? 'unloaded' : 'failed'
        node.failedAt = performance.now()
        return
      }
      const sorted = sortSplatRecords(buf, viewDir[0], viewDir[1], viewDir[2])
      node.bytes = sorted
      node.sortedDirX = viewDir[0]
      node.sortedDirY = viewDir[1]
      node.sortedDirZ = viewDir[2]
      try {
        this.uploadNode(node)
      } catch {
        // context loss mid-upload: release whatever was acquired and retry later
        this.evictNode(node)
        node.state = 'failed'
        node.failedAt = performance.now()
        return
      }
      node.state = 'ready'
      node.firstDrawnAt = 0 // fade anchors to the first frame actually drawn
      this.map?.triggerRepaint()
    })
  }

  private uploadNode(node: SplatNode): void {
    const gl = this.gl as WebGL2RenderingContext
    const pool = this.pool as BufferPool
    const bytes = node.bytes as ArrayBuffer
    node.splatCount = bytes.byteLength / SPLAT_STRIDE

    let buffer: WebGLBuffer
    if (bytes.byteLength <= SLOT_BYTES) {
      node.slot = pool.acquire(new Uint8Array(bytes))
      buffer = node.slot.buffer
    } else {
      // oversize node (rare): dedicated buffer outside the ring. The handle is
      // kept on the node — ARRAY_BUFFER binding is NOT VAO state in WebGL2, so
      // it can never be recovered from the VAO later.
      const b = gl.createBuffer()
      if (!b) throw new Error('createBuffer failed')
      gl.bindBuffer(gl.ARRAY_BUFFER, b)
      gl.bufferData(gl.ARRAY_BUFFER, new Uint8Array(bytes), gl.DYNAMIC_DRAW)
      this.oversize.add(b)
      buffer = b
      node.slot = null
      node.glBuffer = b
    }
    this.residentBytes += bytes.byteLength

    const vao = gl.createVertexArray()
    if (!vao) throw new Error('createVertexArray failed')
    gl.bindVertexArray(vao)
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer)
    gl.enableVertexAttribArray(0)
    gl.vertexAttribPointer(0, 3, gl.FLOAT, false, SPLAT_STRIDE, 0)
    gl.vertexAttribDivisor(0, 1)
    gl.enableVertexAttribArray(1)
    gl.vertexAttribPointer(1, 3, gl.FLOAT, false, SPLAT_STRIDE, 12)
    gl.vertexAttribDivisor(1, 1)
    gl.enableVertexAttribArray(2)
    gl.vertexAttribPointer(2, 4, gl.UNSIGNED_BYTE, true, SPLAT_STRIDE, 24)
    gl.vertexAttribDivisor(2, 1)
    gl.enableVertexAttribArray(3)
    gl.vertexAttribPointer(3, 4, gl.UNSIGNED_BYTE, true, SPLAT_STRIDE, 28)
    gl.vertexAttribDivisor(3, 1)
    gl.bindVertexArray(null)
    gl.bindBuffer(gl.ARRAY_BUFFER, null)
    node.vao = vao
  }

  private evictNode(node: SplatNode): void {
    const gl = this.gl
    if (node.bytes) this.residentBytes -= node.bytes.byteLength
    if (node.slot && this.pool) this.pool.release(node.slot)
    if (node.glBuffer && gl) {
      gl.deleteBuffer(node.glBuffer)
      this.oversize.delete(node.glBuffer)
    }
    if (node.vao && gl) gl.deleteVertexArray(node.vao)
    node.slot = null
    node.glBuffer = null
    node.vao = null
    node.bytes = null
    if (node.state === 'ready' || node.state === 'loading') node.state = 'unloaded'
    node.splatCount = 0
  }

  // -------------------------------------------------------------- per frame

  /** Camera position in ENU, recovered from the inverted frame matrix: the
   *  unprojected near point of the view-center ray sits within nearZ metres
   *  of the optical centre — exact enough for SSE and sort ordering. */
  private cameraEnuFrom(enuMat: Mat4): [number, number, number] {
    const inv = invert(enuMat)
    if (!inv) return [0, 0, 1000]
    const p = transformPoint(inv, [0, 0, -0.9999])
    return [p[0], p[1], p[2]]
  }

  private ensureZOffset(node: SplatNode): void {
    if (node.zOffsetReliable) return
    const map = this.map as MLMap
    const m = this.manifest as TilesetManifest
    const latRad = (m.origin.lat * Math.PI) / 180
    const lon = m.origin.lon + node.cx / (METERS_PER_DEG_LON_EQ * Math.cos(latRad))
    const lat = m.origin.lat + node.cy / METERS_PER_DEG_LAT
    let elev: number | null = null
    try {
      elev = map.queryTerrainElevation([lon, lat])
    } catch {
      elev = null
    }
    const baseAMSL = this.originAltAMSL() + node.baseZ
    if (elev === null) {
      // terrain disabled: clamp the content base to the z=0 ground plane
      node.zOffset = -baseAMSL
      node.zOffsetReliable = true
      return
    }
    // terrain enabled — but queryTerrainElevation returns 0 (not null) while
    // DEM tiles are still streaming; caching that would bury the node at sea
    // level for the whole session. Only trust the sample once tiles settled.
    node.zOffset = elev - baseAMSL
    node.zOffsetReliable = map.areTilesLoaded()
    if (!node.zOffsetReliable) this.map?.triggerRepaint()
  }

  /** The full ENU→clip matrix for this frame (float64). */
  private enuMatrix(args: CustomRenderMethodInput): Mat4 {
    const o = this.originMerc as { x: number; y: number; z: number }
    const s = this.metersToMerc
    const main = args.defaultProjectionData.mainMatrix as unknown as ArrayLike<number>
    const m = new Float64Array(16)
    for (let i = 0; i < 16; i++) m[i] = main[i]
    // mercator y grows south → ENU north needs the negative scale
    return composeTRS(m, [o.x, o.y, o.z], [s, -s, s])
  }

  render(gl: WebGLRenderingContext | WebGL2RenderingContext,
         args: CustomRenderMethodInput): void {
    if (!this.enabled || !this.tileset || !this.originMerc || !this.program) return
    const gl2 = gl as WebGL2RenderingContext
    const map = this.map as MLMap
    this.frame++
    this.intersector?.updateMatrix(args, this.originMerc, this.metersToMerc,
      this.originAltAMSL())

    const enuMat = this.enuMatrix(args)
    this.matrixF32.set(enuMat)
    const planes = extractFrustumPlanes(enuMat)
    const cam = this.cameraEnuFrom(enuMat)
    const canvas = map.getCanvas()
    const vw = canvas.width
    const vh = canvas.height
    const fov = args.fov || 0.6435 // vertical fov, radians

    // ---------- SSE traversal (REPLACE refinement with cross-fade) ----------
    const now = performance.now()
    const drawList: { node: SplatNode; dist: number; fade: number }[] = []
    const fadeOf = (n: SplatNode): number =>
      n.firstDrawnAt === 0 ? 0 : Math.min(1, (now - n.firstDrawnAt) / FADE_MS)

    const pushDraw = (node: SplatNode, dist: number, fade: number): void => {
      if (node.firstDrawnAt === 0) node.firstDrawnAt = now
      drawList.push({ node, dist, fade })
    }

    const visit = (node: SplatNode): void => {
      const radius = Math.hypot(node.hx, node.hy, node.hz)
      const zOff = Number.isNaN(node.zOffset) ? 0 : node.zOffset
      if (!sphereInFrustum(planes, node.cx, node.cy, node.cz + zOff, radius + 30)) return
      // every traversed node is "in use" — descended-past ancestors must never
      // be evicted out from under the rendered cut (zoom-out would blank)
      node.lastUsedFrame = this.frame
      const dist = pointToBoxDistance(cam[0], cam[1], cam[2],
        node.cx - node.hx, node.cy - node.hy, node.cz - node.hz,
        node.cx + node.hx, node.cy + node.hy, node.cz + node.hz)
      const sse = screenSpaceError(node.geometricError, dist, vh, fov)

      if (node.children.length > 0 && sse > SSE_THRESHOLD_PX) {
        const dir = this.viewDirTo(node, cam)
        let allReady = true
        for (const c of node.children) {
          if (c.state !== 'ready') {
            allReady = false
            this.requestLoad(c, dir)
          }
        }
        if (allReady) {
          // cross-fade: while any child is still fading in, keep the parent
          // up at the complementary opacity — replaces the pop/hole with a
          // brief intentional double-blend
          let minChildFade = 1
          for (const c of node.children) minChildFade = Math.min(minChildFade, fadeOf(c))
          if (minChildFade < 1 && node.state === 'ready') {
            pushDraw(node, dist, 1 - minChildFade)
          }
          for (const c of node.children) visit(c)
          return
        }
        // children still streaming — fall through and show this node meanwhile
      }
      if (node.state === 'ready') {
        pushDraw(node, dist, fadeOf(node) || (node.firstDrawnAt === 0 ? 0 : 1))
      } else {
        this.requestLoad(node, this.viewDirTo(node, cam))
        // zoom-out fallback: this coarse node isn't resident yet, but its
        // (previously refined) descendants may be — draw them instead of
        // leaving a hole for a full network round-trip
        for (const c of node.children) visit(c)
      }
    }
    visit(this.tileset.root)

    if (drawList.length === 0) {
      this.evictPass()
      return
    }

    // ---------- draw: nodes back-to-front ----------
    drawList.sort((a, b) => b.dist - a.dist)
    let animating = false

    gl2.useProgram(this.program)
    gl2.uniformMatrix4fv(this.uniforms.u_matrix, false, this.matrixF32)
    gl2.uniform2f(this.uniforms.u_viewport, vw, vh)
    gl2.enable(gl2.BLEND)
    gl2.blendFunc(gl2.ONE, gl2.ONE_MINUS_SRC_ALPHA)
    gl2.depthMask(false) // depth TEST stays on (terrain occludes splats)

    for (const { node, fade } of drawList) {
      this.ensureZOffset(node)
      const f = fade === 0 ? fadeOf(node) : fade
      if (f < 1) animating = true
      gl2.uniform1f(this.uniforms.u_fade, f)
      gl2.uniform1f(this.uniforms.u_zOffset, Number.isNaN(node.zOffset) ? 0 : node.zOffset)
      gl2.bindVertexArray(node.vao)
      gl2.drawArraysInstanced(gl2.TRIANGLE_STRIP, 0, 4, node.splatCount)
    }
    gl2.bindVertexArray(null)
    gl2.depthMask(true) // restore MapLibre's expected state

    // ---------- async maintenance ----------
    this.resortPass(drawList, cam)
    this.evictPass()
    if (animating) map.triggerRepaint()
  }

  private viewDirTo(node: SplatNode, cam: [number, number, number]
                    ): [number, number, number] {
    const dx = node.cx - cam[0]
    const dy = node.cy - cam[1]
    const dz = node.cz - cam[2]
    const len = Math.hypot(dx, dy, dz) || 1
    return [dx / len, dy / len, dz / len]
  }

  /** Re-sort at most ONE stale node per frame (nearest first) — keeps blending
   *  correct during orbit without ever blocking the frame budget. */
  private resortPass(drawList: { node: SplatNode; dist: number }[],
                     cam: [number, number, number]): void {
    let candidate: SplatNode | null = null
    let candidateDist = Infinity
    for (const { node, dist } of drawList) {
      if (!node.bytes) continue
      const dir = this.viewDirTo(node, cam)
      const dot = dir[0] * node.sortedDirX + dir[1] * node.sortedDirY + dir[2] * node.sortedDirZ
      if (dot < RESORT_DOT_THRESHOLD && dist < candidateDist) {
        candidate = node
        candidateDist = dist
      }
    }
    if (!candidate || !this.pool) return
    const dir = this.viewDirTo(candidate, cam)
    const sorted = sortSplatRecords(candidate.bytes as ArrayBuffer, dir[0], dir[1], dir[2])
    candidate.bytes = sorted
    candidate.sortedDirX = dir[0]
    candidate.sortedDirY = dir[1]
    candidate.sortedDirZ = dir[2]
    if (candidate.slot) {
      this.pool.rewrite(candidate.slot, new Uint8Array(sorted))
    } else if (this.gl && candidate.glBuffer) {
      // oversize node path — the handle is kept on the node because the
      // ARRAY_BUFFER binding is NOT VAO state and cannot be recovered later
      const gl = this.gl
      gl.bindBuffer(gl.ARRAY_BUFFER, candidate.glBuffer)
      gl.bufferSubData(gl.ARRAY_BUFFER, 0, new Uint8Array(sorted))
      gl.bindBuffer(gl.ARRAY_BUFFER, null)
    }
    this.map?.triggerRepaint()
  }

  /** LRU eviction keeps pooled GPU residency under the byte cap. */
  private evictPass(): void {
    if (!this.tileset || this.residentBytes <= RESIDENT_BYTE_CAP) return
    const candidates = this.tileset.nodes
      .filter((n) => n.state === 'ready' && n.lastUsedFrame < this.frame - 30)
      .sort((a, b) => a.lastUsedFrame - b.lastUsedFrame)
    for (const n of candidates) {
      if (this.residentBytes <= RESIDENT_BYTE_CAP * 0.85) break
      this.evictNode(n)
    }
  }

  /** Expose the current ENU frame for the picking layer. */
  getPickingContext(): {
    origin: { lon: number; lat: number; altAMSL: number }
    metersToMerc: number
    originMerc: { x: number; y: number; z: number }
  } | null {
    if (!this.manifest || !this.originMerc) return null
    return {
      origin: {
        lon: this.manifest.origin.lon,
        lat: this.manifest.origin.lat,
        altAMSL: this.originAltAMSL(),
      },
      metersToMerc: this.metersToMerc,
      originMerc: this.originMerc,
    }
  }
}
