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
import { NodeTextureManager } from './texturing'
import type { SpatialIntersector } from './spatial_intersector'

const SSE_THRESHOLD_PX = 14
const FADE_MS = 250
const SLOT_BYTES = 14000 * SPLAT_STRIDE // matches pipeline leaf_max
const RESIDENT_BYTE_CAP = 144 * 1024 * 1024
// Radial sort keys are rotation-invariant — only camera TRANSLATION makes a
// node's order stale: when the move exceeds ~10% of the node's distance (or
// 4 m absolute near the ground), the relative depth error becomes visible.
const RESORT_MIN_M = 4
const RESORT_DIST_FRAC = 0.1
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
  private texturesEnabled = true
  private texMan: NodeTextureManager | null = null
  private fallbackTex: WebGLTexture | null = null // 1px — keeps the sampler valid
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

  // Fetched+sorted nodes awaiting RENDER-TIME GPU upload. Fetch continuations
  // are CPU-only: a buffer/VAO upload running in a microtask between frames
  // mutates GL state behind MapLibre's Context cache (same failure class as
  // the async texture upload — see texturing.ts header). render() drains this
  // queue inside its state envelope.
  private pendingUploads: { node: SplatNode; gen: number }[] = []
  private static readonly UPLOAD_BUDGET_PER_FRAME = 6
  private static readonly TEX_PUBLISH_BUDGET_PER_FRAME = 4

  // Per-source presentation: the committed LARIAC corpus carries a baked
  // civic-score tint (neutralized in-shader, TRUTH-001) and projects pre-fire
  // aerial imagery; a post-fire USGS surfel source carries honest hillshade
  // color and must NOT get pre-fire photo texture projected onto it.
  private bakedColor = false

  // Render evidence for E2E/benchmarks (SPATIAL-001/002): cumulative frames
  // with content, nodes drawn, and splat instances issued via
  // drawArraysInstanced. Read through window.__splats / window.__usgsSplats.
  readonly stats = { frames: 0, drawnNodes: 0, drawnSplats: 0, residentBytes: 0 }

  constructor(id: string, baseUrl: string, intersector?: SpatialIntersector,
              opts?: { bakedColor?: boolean; textures?: boolean }) {
    this.id = id
    this.baseUrl = baseUrl.replace(/\/$/, '')
    this.fetcher = new TileFetcher(this.baseUrl)
    this.intersector = intersector ?? null
    this.bakedColor = opts?.bakedColor ?? false
    this.texturesEnabled = opts?.textures ?? true
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
    for (const name of ['u_matrix', 'u_viewport', 'u_fade', 'u_zOffset',
                        'u_hasTex', 'u_texOrigin', 'u_texInvSize', 'u_tex',
                        'u_bakedColor']) {
      this.uniforms[name] = gl.getUniformLocation(this.program, name)
    }
    this.pool = new BufferPool(gl, 16, 8)
    this.texMan = new NodeTextureManager(gl, () => map.triggerRepaint())
    // 1×1 fallback keeps the sampler valid on un-textured draws. Restore the
    // previous binding (NOT null) — MapLibre's state cache must stay truthful.
    const prevTex = gl.getParameter(gl.TEXTURE_BINDING_2D) as WebGLTexture | null
    this.fallbackTex = gl.createTexture()
    gl.bindTexture(gl.TEXTURE_2D, this.fallbackTex)
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, 1, 1, 0, gl.RGBA, gl.UNSIGNED_BYTE,
      new Uint8Array([128, 128, 128, 255]))
    gl.bindTexture(gl.TEXTURE_2D, prevTex)
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
    this.texMan?.destroy()
    this.texMan = null
    if (this.fallbackTex) gl2.deleteTexture(this.fallbackTex)
    this.fallbackTex = null
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

  private requestLoad(node: SplatNode, cam: [number, number, number]): void {
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
      // CPU-only continuation: sort, park the bytes, and queue the node for a
      // render-time upload. No gl.* calls on this (async) path.
      const sorted = sortSplatRecords(buf, cam[0], cam[1], cam[2])
      node.bytes = sorted
      node.sortedCamX = cam[0]
      node.sortedCamY = cam[1]
      node.sortedCamZ = cam[2]
      this.pendingUploads.push({ node, gen })
      this.map?.triggerRepaint()
    })
  }

  /** Render-time drain of fetched nodes (inside the GL state envelope).
   *  Returns the number of nodes still queued. */
  private drainUploads(budget: number): number {
    let done = 0
    while (this.pendingUploads.length > 0 && done < budget) {
      const { node, gen } = this.pendingUploads.shift() as { node: SplatNode; gen: number }
      // stale: layer re-added, or the node was evicted/reset while queued
      if (gen !== this.generation || node.state !== 'loading' || !node.bytes) continue
      try {
        this.uploadNode(node)
      } catch {
        // context loss mid-upload: release whatever was acquired and retry later
        this.evictNode(node)
        node.state = 'failed'
        node.failedAt = performance.now()
        continue
      }
      node.state = 'ready'
      node.firstDrawnAt = 0 // fade anchors to the first frame actually drawn
      for (let p: SplatNode | null = node; p; p = p.parent) p.residentDesc++
      done++
    }
    return this.pendingUploads.length
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
      // slot CAPACITY is the true GPU cost (classes keep waste low)
      this.residentBytes += node.slot.capacity - bytes.byteLength
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
    if (node.state === 'ready') {
      for (let p: SplatNode | null = node; p; p = p.parent) p.residentDesc--
    }
    // mirror uploadNode's accounting: pooled slots cost their CAPACITY on the GPU
    if (node.bytes) this.residentBytes -= node.slot ? node.slot.capacity : node.bytes.byteLength
    if (node.slot && this.pool) this.pool.release(node.slot)
    if (node.glBuffer && gl) {
      gl.deleteBuffer(node.glBuffer)
      this.oversize.delete(node.glBuffer)
    }
    if (node.vao && gl) gl.deleteVertexArray(node.vao)
    this.texMan?.evict(node.id) // the node's aerial texture rides its residency
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

  private static readonly CLAMP_MAX_NODE_M = 600

  private ensureZOffset(node: SplatNode): void {
    if (node.zOffsetReliable) return
    // A single centre-sampled offset is only meaningful for nodes much smaller
    // than the terrain relief wavelength. Multi-km internal nodes straddle
    // canyons AND ridges — clamping them by their centre elevation hoists
    // coastal content hundreds of metres into the sky (the "floating blobs").
    // Their absolute AMSL heights are already correct: leave them unclamped.
    if (node.hx * 2 > SplatRenderLayer.CLAMP_MAX_NODE_M) {
      node.zOffset = 0
      node.zOffsetReliable = true
      return
    }
    // throttle: while the DEM is still streaming, probe at most every 15
    // frames per node instead of spinning the render loop every frame
    if (this.frame - node.lastZProbeFrame < 15) return
    node.lastZProbeFrame = this.frame

    const map = this.map as MLMap
    const m = this.manifest as TilesetManifest
    const latRad = (m.origin.lat * Math.PI) / 180
    const lon = m.origin.lon + node.cx / (METERS_PER_DEG_LON_EQ * Math.cos(latRad))
    const lat = m.origin.lat + node.cy / METERS_PER_DEG_LAT
    let elev: number | null
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
    const prev = node.zOffset
    node.zOffset = elev - baseAMSL
    node.zOffsetReliable = map.areTilesLoaded()
    if (!node.zOffsetReliable &&
        (Number.isNaN(prev) || Math.abs(prev - node.zOffset) > 0.25)) {
      this.map?.triggerRepaint()
    }
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

    // ---- snapshot the GL state we mutate (ALWAYS, before any gl.* below) ----
    // MapLibre v5's Context CACHES blend/depth/texture/buffer/program state and
    // skips "redundant" sets. Raw mutations desync that cache, so MapLibre's
    // next pass (the terrain drape that carries the ground imagery) randomly
    // runs with OUR state. Every GL-mutating path — texture publishes, buffer
    // uploads, draws, re-sorts, evictions — runs between this snapshot and
    // restore(), which re-asserts the exact values (cache == hardware).
    const prev = {
      blendOn: gl2.isEnabled(gl2.BLEND),
      srcRGB: gl2.getParameter(gl2.BLEND_SRC_RGB) as number,
      dstRGB: gl2.getParameter(gl2.BLEND_DST_RGB) as number,
      srcA: gl2.getParameter(gl2.BLEND_SRC_ALPHA) as number,
      dstA: gl2.getParameter(gl2.BLEND_DST_ALPHA) as number,
      depthMask: gl2.getParameter(gl2.DEPTH_WRITEMASK) as boolean,
      activeTexture: gl2.getParameter(gl2.ACTIVE_TEXTURE) as number,
      program: gl2.getParameter(gl2.CURRENT_PROGRAM) as WebGLProgram | null,
      vao: gl2.getParameter(gl2.VERTEX_ARRAY_BINDING) as WebGLVertexArrayObject | null,
      arrayBuffer: gl2.getParameter(gl2.ARRAY_BUFFER_BINDING) as WebGLBuffer | null,
    }
    gl2.activeTexture(gl2.TEXTURE0)
    const prevTex0 = gl2.getParameter(gl2.TEXTURE_BINDING_2D) as WebGLTexture | null
    const restore = (): void => {
      gl2.bindVertexArray(prev.vao)
      gl2.bindBuffer(gl2.ARRAY_BUFFER, prev.arrayBuffer)
      gl2.activeTexture(gl2.TEXTURE0)
      gl2.bindTexture(gl2.TEXTURE_2D, prevTex0)
      gl2.activeTexture(prev.activeTexture)
      gl2.useProgram(prev.program)
      gl2.blendFuncSeparate(prev.srcRGB, prev.dstRGB, prev.srcA, prev.dstA)
      if (prev.blendOn) gl2.enable(gl2.BLEND)
      else gl2.disable(gl2.BLEND)
      gl2.depthMask(prev.depthMask)
    }
    let animating = false

    // ---- render-time GPU maintenance: drain the two-phase publish queues ----
    const texPending = this.texMan
      ? this.texMan.publishPending(SplatRenderLayer.TEX_PUBLISH_BUDGET_PER_FRAME)
      : 0
    const uploadsPending = this.drainUploads(SplatRenderLayer.UPLOAD_BUDGET_PER_FRAME)
    if (texPending > 0 || uploadsPending > 0) map.triggerRepaint()

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
        let allReady = true
        for (const c of node.children) {
          if (c.state !== 'ready') {
            allReady = false
            this.requestLoad(c, cam)
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
        this.requestLoad(node, cam)
        // zoom-out fallback: draw previously-refined descendants instead of a
        // hole — but ONLY where resident content already exists. Recursing
        // into unloaded subtrees here used to flood-request the entire tree
        // on startup (2,375 fetches + main-thread sorts: the fan spinner).
        for (const c of node.children) {
          if (c.residentDesc > 0) visit(c)
        }
      }
    }
    visit(this.tileset.root)

    if (drawList.length === 0) {
      this.evictPass()
      restore()
      return
    }

    // ---------- draw: nodes back-to-front ----------
    drawList.sort((a, b) => b.dist - a.dist)

    gl2.useProgram(this.program)
    gl2.uniformMatrix4fv(this.uniforms.u_matrix, false, this.matrixF32)
    gl2.uniform2f(this.uniforms.u_viewport, vw, vh)
    gl2.uniform1i(this.uniforms.u_tex, 0)
    gl2.uniform1f(this.uniforms.u_bakedColor, this.bakedColor ? 1 : 0)
    gl2.enable(gl2.BLEND)
    gl2.blendFunc(gl2.ONE, gl2.ONE_MINUS_SRC_ALPHA)
    gl2.depthMask(false) // depth TEST stays on (terrain occludes splats)

    const m = this.manifest as TilesetManifest
    for (const { node, dist, fade } of drawList) {
      this.ensureZOffset(node)
      const f = fade === 0 ? fadeOf(node) : fade
      if (f < 1) animating = true
      gl2.uniform1f(this.uniforms.u_fade, f)
      gl2.uniform1f(this.uniforms.u_zOffset, Number.isNaN(node.zOffset) ? 0 : node.zOffset)

      // projective aerial texture for any node small enough that a 256px
      // compose keeps useful texel density (≈1.5 m/px at 400 m). The rendered
      // SSE cut mostly sits on internal nodes, so gating on leaf-ness alone
      // would almost never texture anything; size is the correct gate (and it
      // bounds texture residency the same way).
      let bound = false
      if (this.texturesEnabled && this.texMan && node.hx * 2 <= 400 && dist <= 2500) {
        const binding = this.texMan.acquire(
          node.id, this.frame,
          node.cx - node.hx, node.cy - node.hy,
          node.cx + node.hx, node.cy + node.hy,
          m.origin.lon, m.origin.lat)
        if (binding) {
          gl2.bindTexture(gl2.TEXTURE_2D, binding.texture)
          gl2.uniform1f(this.uniforms.u_hasTex, 1)
          gl2.uniform2f(this.uniforms.u_texOrigin, binding.originEnu[0], binding.originEnu[1])
          gl2.uniform2f(this.uniforms.u_texInvSize, binding.invSizeEnu[0], binding.invSizeEnu[1])
          bound = true
        }
      }
      if (!bound) {
        gl2.bindTexture(gl2.TEXTURE_2D, this.fallbackTex)
        gl2.uniform1f(this.uniforms.u_hasTex, 0)
        gl2.uniform2f(this.uniforms.u_texOrigin, 0, 0)
        gl2.uniform2f(this.uniforms.u_texInvSize, 0, 0)
      }

      gl2.bindVertexArray(node.vao)
      gl2.drawArraysInstanced(gl2.TRIANGLE_STRIP, 0, 4, node.splatCount)
      this.stats.drawnNodes++
      this.stats.drawnSplats += node.splatCount
    }
    this.stats.frames++
    this.stats.residentBytes = this.residentBytes
    // ---- GPU maintenance still inside the envelope (binds buffers, deletes) ----
    this.resortPass(drawList, cam)
    this.evictPass()
    // ---- restore the exact pre-render state (keeps MapLibre's cache valid) ----
    restore()
    if (animating) map.triggerRepaint()
  }

  /** Re-sort a small batch of the stalest nearby nodes per frame. A budget of
   *  one node kept the render loop warm for hundreds of frames after every
   *  camera move (each resort schedules a repaint to continue the drain) —
   *  four per frame stays well inside the frame budget (~O(n) counting sort,
   *  <1 ms each) and settles the backlog in a fraction of a second. Radial
   *  keys mean pure rotation triggers NO re-sorts at all; only translation
   *  beyond ~10% of a node's distance does. */
  private static readonly RESORT_BUDGET_PER_FRAME = 4

  private resortPass(drawList: { node: SplatNode; dist: number }[],
                     cam: [number, number, number]): void {
    if (!this.pool) return
    const stale: { node: SplatNode; dist: number }[] = []
    for (const { node, dist } of drawList) {
      if (!node.bytes) continue
      const mx = cam[0] - node.sortedCamX
      const my = cam[1] - node.sortedCamY
      const mz = cam[2] - node.sortedCamZ
      const moved2 = mx * mx + my * my + mz * mz
      const thresh = Math.max(RESORT_MIN_M, dist * RESORT_DIST_FRAC)
      if (moved2 > thresh * thresh) stale.push({ node, dist })
    }
    if (stale.length === 0) return
    stale.sort((a, b) => a.dist - b.dist) // nearest (most visible) first
    const batch = stale.slice(0, SplatRenderLayer.RESORT_BUDGET_PER_FRAME)
    for (const { node } of batch) {
      const sorted = sortSplatRecords(node.bytes as ArrayBuffer, cam[0], cam[1], cam[2])
      node.bytes = sorted
      node.sortedCamX = cam[0]
      node.sortedCamY = cam[1]
      node.sortedCamZ = cam[2]
      if (node.slot) {
        this.pool.rewrite(node.slot, new Uint8Array(sorted))
      } else if (this.gl && node.glBuffer) {
        // oversize node path — the handle is kept on the node because the
        // ARRAY_BUFFER binding is NOT VAO state and cannot be recovered later
        const gl = this.gl
        gl.bindBuffer(gl.ARRAY_BUFFER, node.glBuffer)
        gl.bufferSubData(gl.ARRAY_BUFFER, 0, new Uint8Array(sorted))
        gl.bindBuffer(gl.ARRAY_BUFFER, null)
      }
    }
    if (stale.length > batch.length) this.map?.triggerRepaint()
  }

  /** LRU eviction keeps pooled GPU residency under the byte cap. */
  private evictPass(): void {
    if (!this.tileset || this.residentBytes <= RESIDENT_BYTE_CAP) return
    const candidates = this.tileset.nodes
      .filter((n) => n.state === 'ready' && n.lastUsedFrame < this.frame - 120)
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
