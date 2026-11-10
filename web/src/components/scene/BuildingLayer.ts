// MapLibre custom 3D layer drawing the county building model as indexed
// triangle meshes, one draw per batch and pass.
//
// Every per-structure decision lives in two small lookup textures indexed by
// structure id, so changing a score, a selection or a ground correction is a
// texture update and never touches geometry:
//   state  RGBA8  rgb = score colour, a = mode | flags   (format.ts MODE_*)
//   ground R32F   metres added to the structure's heights so it rests on the
//                 terrain MapLibre actually draws
//
// Passes: solid (standing structures, aerial photo on roofs), ghost depth +
// ghost fill (destroyed structures: one even translucent layer, never a stack
// of overlapping faces), edges, and an on-demand 1×1 id pass for picking.
//
// GL discipline: every gl.* call happens inside render(), between a state
// snapshot and its restore. Worker results are queued and uploaded there.

import type { CustomLayerInterface, CustomRenderMethodInput, Map as MLMap } from 'maplibre-gl'
import { extractFrustumPlanes, sphereInFrustum } from '../spatial/frustum'
import { composeTRS, invert, transformPoint, type Mat4 } from '../spatial/mat4'
import {
  EDGE_BYTES,
  FLAG_SELECTED,
  MODE_GHOST,
  MODE_HIDDEN,
  VERTEX_BYTES,
  structureMode,
  type DecodedBatch,
  type SceneManifest,
  type SceneNode,
} from './format'
import { loadSceneManifest } from './manifest'
import { BUILDING_FRAG, BUILDING_VERT, EDGE_FRAG, EDGE_VERT, compile } from './shaders'
import type { WorkerRequest, WorkerResponse } from './scene.worker'

export interface ParcelStyle {
  /** score colour as [r, g, b] 0–255, or null when the parcel has no score */
  color: [number, number, number] | null
  destroyed: boolean
}

export interface BuildingLayerOptions {
  /** `{z}/{x}/{y}` aerial tiles projected onto the roofs of standing structures */
  aerialTemplate?: string
  /**
   * Depth bias for the ghost passes. Destroyed structures are drawn where
   * their foundations meet steep ground; without a bias the hillside slices
   * through the shell. `factor`/`units` are glPolygonOffset arguments
   * (slope-scaled, negative = toward the camera); `line` is the extra
   * clip-space pull that keeps edge lines above their own faces.
   */
  ghostDepthBias?: { factor: number; units: number; line: number }
  /** edge line width in CSS pixels */
  edgeWidth?: number
}

const PASS_SOLID = 0
const PASS_GHOST_DEPTH = 1
const PASS_GHOST_FILL = 2
const PASS_PICK = 4

const LUT_WIDTH = 4096
const MAX_BATCH_LOADS = 4
const MAX_ATLAS_LOADS = 2
// Beyond this a structure is a few pixels: its batch is neither fetched nor drawn.
const LOAD_DISTANCE_M = 3200
// Roof photos only matter up close, and each is a multi-megabyte texture.
const ATLAS_DISTANCE_M = 1400
const ATLAS_MAX_PX = 2048
const ATLAS_BYTE_CAP = 128 * 1024 * 1024
const GEOMETRY_BYTE_CAP = 256 * 1024 * 1024
const BATCH_UPLOADS_PER_FRAME = 2
const GROUND_SAMPLES_PER_FRAME = 64
/** residual below which a baked ground delta is trusted as is */
const GROUND_TOLERANCE_M = 0.5
const FAIL_RETRY_MS = 15_000

interface Batch {
  node: SceneNode
  /** local metres: centre and radius of the bounding sphere */
  cx: number
  cy: number
  cz: number
  radius: number
  state: 'idle' | 'loading' | 'ready' | 'failed'
  failedAt: number
  requestId: number
  pending: DecodedBatch | null
  vao: WebGLVertexArrayObject | null
  vbo: WebGLBuffer | null
  ibo: WebGLBuffer | null
  edgeVao: WebGLVertexArrayObject | null
  edgeVbo: WebGLBuffer | null
  indexCount: number
  edgeCount: number
  gpuBytes: number
  grid: DecodedBatch['grid'] | null
  structures: Uint16Array | null
  hasSolid: boolean
  atlas: WebGLTexture | null
  atlasState: 'idle' | 'loading' | 'ready' | 'failed'
  atlasPending: ImageBitmap | null
  atlasBytes: number
  atlasRequestId: number
  lastUsedFrame: number
  matrix: Float32Array
}

export class BuildingLayer implements CustomLayerInterface {
  readonly id: string
  readonly type = 'custom' as const
  readonly renderingMode = '3d' as const

  private map: MLMap | null = null
  private gl: WebGL2RenderingContext | null = null
  private program: WebGLProgram | null = null
  private uniforms: Record<string, WebGLUniformLocation | null> = {}
  private edgeProgram: WebGLProgram | null = null
  private edgeUniforms: Record<string, WebGLUniformLocation | null> = {}
  private readonly edgeWidth: number
  private worker: Worker | null = null
  private manifest: SceneManifest | null = null
  private batches: Batch[] = []
  private byRequest = new Map<number, { batch: Batch; kind: 'batch' | 'atlas' }>()
  private nextRequestId = 1
  private generation = 0
  private frame = 0
  private enabled = true

  private readonly baseUrl: string
  private readonly aerialTemplate: string | null
  private readonly bias: { factor: number; units: number; line: number }

  // per-structure tables, indexed by structure id
  private lutHeight = 1
  private stateBytes = new Uint8Array(0)
  private stateTex: WebGLTexture | null = null
  private stateDirty = false
  private groundDelta = new Float32Array(0)
  private groundTex: WebGLTexture | null = null
  private groundDirty = false
  private baseZ = new Float32Array(0)
  /** terrain at each structure's centre that its ground delta assumes */
  private expectedGround = new Float32Array(0)
  private groundCorrection = new Float32Array(0)
  private centers = new Float64Array(0)
  private sampledEpoch = new Int32Array(0)
  private groundEpoch = 1
  private groundCursor = 0
  private lastZoomBucket = -1
  private apnToIds = new Map<string, number[]>()
  private idToApn: string[] = []
  private structureDamage: string[] = []
  private parcels: Map<string, ParcelStyle> | null = null
  private selectedApn: string | null = null
  private fallbackTex: WebGLTexture | null = null
  /** local metres → clip for the frame being drawn */
  private localMatrix: Mat4 = new Float64Array(16)

  // picking
  private pickFbo: WebGLFramebuffer | null = null
  private pickColor: WebGLTexture | null = null
  private pickDepth: WebGLRenderbuffer | null = null
  private pickRequests: { x: number; y: number; resolve: (apn: string | null) => void }[] = []
  // id pixels on their way back from the GPU. A synchronous readPixels makes
  // the main thread wait for the whole frame to finish rendering; a pixel
  // buffer and a fence return the same answer a frame or two later for free.
  private pickReads: { buffer: WebGLBuffer; sync: WebGLSync; resolve: (apn: string | null) => void }[] = []

  /** Counters for checks and benchmarks (`window.__buildings.stats`). */
  readonly stats = {
    frames: 0,
    drawCalls: 0,
    triangles: 0,
    batchesReady: 0,
    batchesDrawn: 0,
    geometryBytes: 0,
    atlasBytes: 0,
    groundSamples: 0,
    groundCorrections: 0,
    lastRenderMs: 0,
    lastPickMs: 0,
    errors: [] as string[],
  }

  private onTerrain = (): void => {
    this.groundEpoch++
    this.map?.triggerRepaint()
  }

  constructor(id: string, baseUrl: string, options: BuildingLayerOptions = {}) {
    this.id = id
    this.baseUrl = baseUrl.replace(/\/$/, '')
    this.aerialTemplate = options.aerialTemplate ?? null
    this.bias = options.ghostDepthBias ?? { factor: -2, units: -64, line: 6e-5 }
    this.edgeWidth = options.edgeWidth ?? 1.4
  }

  // ------------------------------------------------------------------ api

  setEnabled(on: boolean): void {
    this.enabled = on
    if (!on) this.abandonPicks() // a disabled layer does not render, so nothing would collect them
    this.map?.triggerRepaint()
  }

  /** Score colour and damage per APN. Safe before the manifest has loaded. */
  setParcels(parcels: Map<string, ParcelStyle>): void {
    this.parcels = parcels
    this.rebuildState()
  }

  select(apn: string | null): void {
    if (apn === this.selectedApn) return
    this.selectedApn = apn
    this.rebuildState()
  }

  /** APN of the structure drawn at a canvas position (CSS pixels), if any. */
  pick(point: { x: number; y: number }): Promise<string | null> {
    if (!this.map || !this.program || !this.enabled) return Promise.resolve(null)
    return new Promise((resolve) => {
      this.pickRequests.push({ x: point.x, y: point.y, resolve })
      this.map?.triggerRepaint()
    })
  }

  private abandonPicks(): void {
    for (const request of this.pickRequests) request.resolve(null)
    this.pickRequests = []
    for (const read of this.pickReads) {
      this.gl?.deleteSync(read.sync)
      this.gl?.deleteBuffer(read.buffer)
      read.resolve(null)
    }
    this.pickReads = []
  }

  // ---------------------------------------------------------------- setup

  onAdd(map: MLMap, gl: WebGLRenderingContext | WebGL2RenderingContext): void {
    if (!(gl instanceof WebGL2RenderingContext)) {
      throw new Error('BuildingLayer requires a WebGL2 context')
    }
    this.map = map
    this.gl = gl
    const generation = ++this.generation
    this.program = compile(gl, BUILDING_VERT, BUILDING_FRAG)
    for (const name of ['u_matrix', 'u_gridPerMetreZ', 'u_pass', 'u_state', 'u_ground',
                        'u_aerial', 'u_hasAerial']) {
      this.uniforms[name] = gl.getUniformLocation(this.program, name)
    }
    this.edgeProgram = compile(gl, EDGE_VERT, EDGE_FRAG)
    for (const name of ['u_matrix', 'u_gridPerMetreZ', 'u_viewport', 'u_width', 'u_lineBias',
                        'u_state', 'u_ground']) {
      this.edgeUniforms[name] = gl.getUniformLocation(this.edgeProgram, name)
    }
    map.on('terrain', this.onTerrain)

    this.worker = new Worker(new URL('./scene.worker.ts', import.meta.url), { type: 'module' })
    this.worker.onmessage = (event: MessageEvent<WorkerResponse>) => this.onWorker(event.data)

    void (async () => {
      try {
        const manifest = await loadSceneManifest(this.baseUrl)
        if (generation !== this.generation) return
        this.adopt(manifest)
        map.triggerRepaint()
      } catch (error) {
        this.fail(error)
      }
    })()
  }

  private adopt(manifest: SceneManifest): void {
    this.manifest = manifest
    const [ox, oy] = manifest.mercator_origin
    const s = manifest.mercator_metre_scale
    const localX = (lon: number): number => ((lon + 180) / 360 - ox) / s
    const localY = (lat: number): number => {
      const rad = (lat * Math.PI) / 180
      return ((1 - Math.log(Math.tan(rad) + 1 / Math.cos(rad)) / Math.PI) / 2 - oy) / s
    }
    this.batches = manifest.nodes.map((node) => {
      const [west, south, east, north] = node.bounds
      const x0 = localX(west), x1 = localX(east)
      const y0 = localY(north), y1 = localY(south)
      return {
        node,
        cx: (x0 + x1) / 2,
        cy: (y0 + y1) / 2,
        cz: 300,
        // heights are unknown until the batch loads: cover sea level to the ridge
        radius: Math.hypot((x1 - x0) / 2, (y1 - y0) / 2, 500),
        state: 'idle', failedAt: 0, requestId: 0, pending: null,
        vao: null, vbo: null, ibo: null, edgeVao: null, edgeVbo: null,
        indexCount: 0, edgeCount: 0, gpuBytes: 0, grid: null, structures: null,
        hasSolid: false,
        atlas: null, atlasState: 'idle', atlasPending: null, atlasBytes: 0, atlasRequestId: 0,
        lastUsedFrame: 0, matrix: new Float32Array(16),
      } satisfies Batch
    })

    const count = manifest.structures.reduce((m, st) => Math.max(m, st.gpu_id), 0) + 1
    this.lutHeight = Math.ceil(count / LUT_WIDTH)
    const texels = LUT_WIDTH * this.lutHeight
    this.stateBytes = new Uint8Array(texels * 4)
    this.groundDelta = new Float32Array(texels)
    this.baseZ = new Float32Array(texels).fill(Number.NaN)
    this.expectedGround = new Float32Array(texels).fill(Number.NaN)
    this.groundCorrection = new Float32Array(texels)
    this.centers = new Float64Array(texels * 2)
    this.sampledEpoch = new Int32Array(texels)
    this.idToApn = new Array<string>(texels).fill('')
    this.structureDamage = new Array<string>(texels).fill('')
    this.apnToIds.clear()
    for (const st of manifest.structures) {
      const id = st.gpu_id
      this.idToApn[id] = st.apn
      this.structureDamage[id] = st.damage
      this.centers[id * 2] = st.center[0]
      this.centers[id * 2 + 1] = st.center[1]
      if (st.base_m !== undefined) this.baseZ[id] = st.base_m
      if (st.ground_delta_m !== undefined) this.groundDelta[id] = st.ground_delta_m
      if (st.ground_m !== undefined) this.expectedGround[id] = st.ground_m
      const ids = this.apnToIds.get(st.apn)
      if (ids) ids.push(id)
      else this.apnToIds.set(st.apn, [id])
    }
    this.groundDirty = true
    this.rebuildState()
  }

  private rebuildState(): void {
    if (!this.manifest) return
    const state = this.stateBytes
    for (const st of this.manifest.structures) {
      const id = st.gpu_id
      const parcel = this.parcels?.get(st.apn)
      // until parcel data arrives nothing is known about a structure's lot:
      // draw nothing rather than guess
      let mode = this.parcels ? structureMode(st.damage, parcel?.destroyed ?? false) : MODE_HIDDEN
      const color = parcel?.color ?? null
      // a destroyed structure on a lot without a score has no colour to carry
      if (mode === MODE_GHOST && !color) mode = MODE_HIDDEN
      state[id * 4] = color ? color[0] : 150
      state[id * 4 + 1] = color ? color[1] : 150
      state[id * 4 + 2] = color ? color[2] : 150
      state[id * 4 + 3] = mode | (this.selectedApn !== null && st.apn === this.selectedApn ? FLAG_SELECTED : 0)
    }
    this.stateDirty = true
    for (const batch of this.batches) this.classify(batch)
    this.map?.triggerRepaint()
  }

  private classify(batch: Batch): void {
    if (!batch.structures) return
    batch.hasSolid = false
    for (const id of batch.structures) {
      if ((this.stateBytes[id * 4 + 3] & 3) === 1) {
        batch.hasSolid = true
        return
      }
    }
  }

  onRemove(map: MLMap, gl: WebGLRenderingContext | WebGL2RenderingContext): void {
    const gl2 = gl as WebGL2RenderingContext
    map.off('terrain', this.onTerrain)
    this.generation++
    this.worker?.terminate()
    this.worker = null
    for (const batch of this.batches) this.release(gl2, batch)
    this.batches = []
    this.byRequest.clear()
    for (const texture of [this.stateTex, this.groundTex, this.fallbackTex, this.pickColor]) {
      if (texture) gl2.deleteTexture(texture)
    }
    this.stateTex = this.groundTex = this.fallbackTex = this.pickColor = null
    if (this.pickDepth) gl2.deleteRenderbuffer(this.pickDepth)
    if (this.pickFbo) gl2.deleteFramebuffer(this.pickFbo)
    this.pickDepth = null
    this.pickFbo = null
    if (this.program) gl2.deleteProgram(this.program)
    if (this.edgeProgram) gl2.deleteProgram(this.edgeProgram)
    this.program = null
    this.edgeProgram = null
    this.abandonPicks()
    this.manifest = null
    this.map = null
    this.gl = null
  }

  private fail(error: unknown): void {
    const message = error instanceof Error ? error.message : String(error)
    if (this.stats.errors.length < 20) this.stats.errors.push(message)
    console.error('building layer:', message)
  }

  // --------------------------------------------------------------- loading

  private post(message: WorkerRequest): void {
    this.worker?.postMessage(message)
  }

  private onWorker(message: WorkerResponse): void {
    const entry = this.byRequest.get(message.requestId)
    if (!entry) {
      if (message.kind === 'atlas') message.image.close()
      return // cancelled, or from a previous layer lifetime
    }
    this.byRequest.delete(message.requestId)
    const { batch } = entry
    if (message.kind === 'batch') {
      batch.pending = message.batch
    } else if (message.kind === 'atlas') {
      batch.atlasPending = message.image
    } else {
      if (entry.kind === 'batch') {
        batch.state = 'failed'
        batch.failedAt = performance.now()
      } else {
        batch.atlasState = 'failed'
      }
      this.fail(message.message)
    }
    this.map?.triggerRepaint()
  }

  private requestBatch(batch: Batch): void {
    if (!this.manifest) return
    batch.state = 'loading'
    batch.requestId = this.nextRequestId++
    this.byRequest.set(batch.requestId, { batch, kind: 'batch' })
    this.post({
      kind: 'batch', requestId: batch.requestId,
      baseUrl: new URL([this.baseUrl, this.manifest.buffers].filter(Boolean).join('/'), location.href).href,
      schema: this.manifest.schema, node: batch.node,
    })
  }

  private requestAtlas(batch: Batch): void {
    if (!this.aerialTemplate) return
    batch.atlasState = 'loading'
    batch.atlasRequestId = this.nextRequestId++
    this.byRequest.set(batch.atlasRequestId, { batch, kind: 'atlas' })
    this.post({
      kind: 'atlas', requestId: batch.atlasRequestId, node: batch.node,
      template: this.aerialTemplate, maxPx: ATLAS_MAX_PX,
    })
  }

  private upload(gl: WebGL2RenderingContext, batch: Batch): void {
    const data = batch.pending as DecodedBatch
    batch.pending = null
    const vbo = gl.createBuffer()
    const ibo = gl.createBuffer()
    const edgeVbo = gl.createBuffer()
    const vao = gl.createVertexArray()
    const edgeVao = gl.createVertexArray()
    if (!vbo || !ibo || !edgeVbo || !vao || !edgeVao) throw new Error('GPU allocation failed')
    gl.bindVertexArray(vao)
    gl.bindBuffer(gl.ARRAY_BUFFER, vbo)
    gl.bufferData(gl.ARRAY_BUFFER, data.vertices, gl.STATIC_DRAW)
    gl.enableVertexAttribArray(0)
    gl.vertexAttribPointer(0, 3, gl.UNSIGNED_SHORT, false, VERTEX_BYTES, 0)
    gl.enableVertexAttribArray(1)
    gl.vertexAttribPointer(1, 2, gl.BYTE, true, VERTEX_BYTES, 6)
    gl.enableVertexAttribArray(2)
    gl.vertexAttribPointer(2, 1, gl.UNSIGNED_SHORT, false, VERTEX_BYTES, 8)
    gl.enableVertexAttribArray(3)
    gl.vertexAttribPointer(3, 2, gl.UNSIGNED_SHORT, true, VERTEX_BYTES, 10)
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, ibo)
    gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, data.indices, gl.STATIC_DRAW)
    // one instance per edge; the four quad corners come from gl_VertexID
    gl.bindVertexArray(edgeVao)
    gl.bindBuffer(gl.ARRAY_BUFFER, edgeVbo)
    gl.bufferData(gl.ARRAY_BUFFER, data.edges, gl.STATIC_DRAW)
    for (const [location, size, offset] of [[0, 3, 0], [1, 3, 6], [2, 1, 12]] as const) {
      gl.enableVertexAttribArray(location)
      gl.vertexAttribPointer(location, size, gl.UNSIGNED_SHORT, false, EDGE_BYTES, offset)
      gl.vertexAttribDivisor(location, 1)
    }
    gl.bindVertexArray(null)
    batch.vao = vao
    batch.vbo = vbo
    batch.ibo = ibo
    batch.edgeVao = edgeVao
    batch.edgeVbo = edgeVbo
    batch.indexCount = data.indices.length
    batch.edgeCount = data.edgeCount
    batch.gpuBytes = data.vertices.byteLength + data.indices.byteLength + data.edges.byteLength
    batch.grid = data.grid
    // tighten the culling sphere now that real heights are known
    batch.cz = data.grid.min[2] + data.grid.extent[2] / 2
    batch.radius = Math.hypot(data.grid.extent[0], data.grid.extent[1], data.grid.extent[2]) / 2
    batch.cx = data.grid.min[0] + data.grid.extent[0] / 2
    batch.cy = data.grid.min[1] + data.grid.extent[1] / 2
    const ids = new Uint16Array(data.bases.length / 2)
    for (let i = 0; i < ids.length; i++) {
      const id = data.bases[i * 2]
      ids[i] = id
      // sources without a build-time registration: seat the mesh's own lowest
      // vertex on whatever terrain is drawn at the structure's centre
      if (Number.isNaN(this.baseZ[id])) this.baseZ[id] = data.bases[i * 2 + 1]
      if (Number.isNaN(this.expectedGround[id])) this.expectedGround[id] = this.baseZ[id]
    }
    batch.structures = ids
    this.classify(batch)
    batch.state = 'ready'
    this.stats.geometryBytes += batch.gpuBytes
    this.stats.batchesReady++
  }

  private uploadAtlas(gl: WebGL2RenderingContext, batch: Batch): void {
    const image = batch.atlasPending as ImageBitmap
    batch.atlasPending = null
    const texture = gl.createTexture()
    if (!texture) {
      image.close()
      batch.atlasState = 'failed'
      return
    }
    gl.activeTexture(gl.TEXTURE2)
    gl.bindTexture(gl.TEXTURE_2D, texture)
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, image)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE)
    gl.generateMipmap(gl.TEXTURE_2D)
    batch.atlas = texture
    batch.atlasBytes = Math.round(image.width * image.height * 4 * 1.34)
    batch.atlasState = 'ready'
    this.stats.atlasBytes += batch.atlasBytes
    image.close()
  }

  private releaseAtlas(gl: WebGL2RenderingContext, batch: Batch): void {
    if (batch.atlasState === 'loading') {
      this.byRequest.delete(batch.atlasRequestId)
      this.post({ kind: 'cancel', requestId: batch.atlasRequestId })
    }
    if (batch.atlas) {
      gl.deleteTexture(batch.atlas)
      this.stats.atlasBytes -= batch.atlasBytes
    }
    batch.atlasPending?.close()
    batch.atlasPending = null
    batch.atlas = null
    batch.atlasBytes = 0
    batch.atlasState = 'idle'
  }

  private release(gl: WebGL2RenderingContext, batch: Batch): void {
    if (batch.state === 'loading') {
      this.byRequest.delete(batch.requestId)
      this.post({ kind: 'cancel', requestId: batch.requestId })
    }
    this.releaseAtlas(gl, batch)
    if (batch.state === 'ready') {
      this.stats.geometryBytes -= batch.gpuBytes
      this.stats.batchesReady--
    }
    if (batch.vao) gl.deleteVertexArray(batch.vao)
    if (batch.edgeVao) gl.deleteVertexArray(batch.edgeVao)
    for (const buffer of [batch.vbo, batch.ibo, batch.edgeVbo]) if (buffer) gl.deleteBuffer(buffer)
    batch.vao = batch.edgeVao = null
    batch.vbo = batch.ibo = batch.edgeVbo = null
    batch.pending = null
    batch.gpuBytes = 0
    batch.state = 'idle'
  }

  // -------------------------------------------------------- lookup textures

  private publishLuts(gl: WebGL2RenderingContext): void {
    if (this.stateDirty && this.stateBytes.length) {
      gl.activeTexture(gl.TEXTURE0)
      if (!this.stateTex) {
        this.stateTex = gl.createTexture()
        gl.bindTexture(gl.TEXTURE_2D, this.stateTex)
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8, LUT_WIDTH, this.lutHeight, 0,
          gl.RGBA, gl.UNSIGNED_BYTE, this.stateBytes)
        nearest(gl)
      } else {
        gl.bindTexture(gl.TEXTURE_2D, this.stateTex)
        gl.texSubImage2D(gl.TEXTURE_2D, 0, 0, 0, LUT_WIDTH, this.lutHeight,
          gl.RGBA, gl.UNSIGNED_BYTE, this.stateBytes)
      }
      this.stateDirty = false
    }
    if (this.groundDirty && this.groundDelta.length) {
      gl.activeTexture(gl.TEXTURE1)
      if (!this.groundTex) {
        this.groundTex = gl.createTexture()
        gl.bindTexture(gl.TEXTURE_2D, this.groundTex)
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.R32F, LUT_WIDTH, this.lutHeight, 0,
          gl.RED, gl.FLOAT, this.groundDelta)
        nearest(gl)
      } else {
        gl.bindTexture(gl.TEXTURE_2D, this.groundTex)
        gl.texSubImage2D(gl.TEXTURE_2D, 0, 0, 0, LUT_WIDTH, this.lutHeight,
          gl.RED, gl.FLOAT, this.groundDelta)
      }
      this.groundDirty = false
    }
  }

  /**
   * Ground registration, residual pass. The build bakes each structure's
   * terrain delta; this only checks structures in batches being DRAWN, a
   * bounded number per frame, and corrects one when the terrain MapLibre is
   * drawing disagrees with its registered base by more than the tolerance
   * (coarser terrain mesh at low zoom, or a source with no baked delta).
   * Returns true while visible structures remain unchecked.
   */
  private sampleGround(drawn: Batch[]): boolean {
    const map = this.map as MLMap
    if (!map.getTerrain() || drawn.length === 0) return false
    // while DEM tiles stream, queries return 0 rather than null: caching that
    // would bury a structure at sea level
    if (!map.areTilesLoaded()) return true
    const zoomBucket = Math.floor(map.getZoom())
    if (zoomBucket !== this.lastZoomBucket) {
      this.lastZoomBucket = zoomBucket
      this.groundEpoch++ // the terrain mesh changes resolution with zoom
    }
    let budget = GROUND_SAMPLES_PER_FRAME
    let remaining = false
    const start = this.groundCursor % drawn.length
    for (let step = 0; step < drawn.length; step++) {
      const batch = drawn[(start + step) % drawn.length]
      const ids = batch.structures
      if (!ids) continue
      for (const id of ids) {
        if (this.sampledEpoch[id] === this.groundEpoch) continue
        if ((this.stateBytes[id * 4 + 3] & 3) === MODE_HIDDEN) continue
        if (budget === 0) {
          remaining = true
          this.groundCursor = start + step
          return remaining
        }
        budget--
        this.stats.groundSamples++
        // checked for this terrain state whatever the answer: an unanswerable
        // point must not be asked again every frame
        this.sampledEpoch[id] = this.groundEpoch
        const elevation = map.queryTerrainElevation([this.centers[id * 2], this.centers[id * 2 + 1]])
        if (elevation === null) continue
        // how far the terrain being drawn is from the terrain the delta assumed
        const residual = elevation - this.expectedGround[id] - this.groundCorrection[id]
        if (Math.abs(residual) > GROUND_TOLERANCE_M) {
          this.groundCorrection[id] += residual
          this.groundDelta[id] += residual
          this.groundDirty = true
          this.stats.groundCorrections++
        }
      }
    }
    return remaining
  }

  // ---------------------------------------------------------------- render

  render(gl: WebGLRenderingContext | WebGL2RenderingContext,
         args: CustomRenderMethodInput): void {
    const manifest = this.manifest
    if (!this.enabled || !manifest || !this.program) return
    const started = performance.now()
    const gl2 = gl as WebGL2RenderingContext
    const map = this.map as MLMap
    this.frame++

    // ---- which batches matter this frame (local metres, float64) ----
    const main = new Float64Array(16)
    const source = args.defaultProjectionData.mainMatrix as unknown as ArrayLike<number>
    for (let i = 0; i < 16; i++) main[i] = source[i]
    const s = manifest.mercator_metre_scale
    const [ox, oy] = manifest.mercator_origin
    const local: Mat4 = composeTRS(main, [ox, oy, 0], [s, s, s])
    this.localMatrix = local
    const planes = extractFrustumPlanes(local)
    const inverse = invert(local)
    const camera = inverse ? transformPoint(inverse, [0, 0, -0.9999]) : [0, 0, 1000]

    const drawn: Batch[] = []
    const wanted: { batch: Batch; distance: number }[] = []
    let loading = 0
    let atlasLoading = 0
    for (const batch of this.batches) {
      if (batch.state === 'loading') loading++
      if (batch.atlasState === 'loading') atlasLoading++
      if (!sphereInFrustum(planes, batch.cx, batch.cy, batch.cz, batch.radius)) continue
      const distance = Math.max(0,
        Math.hypot(camera[0] - batch.cx, camera[1] - batch.cy, camera[2] - batch.cz) - batch.radius)
      if (distance > LOAD_DISTANCE_M) continue
      batch.lastUsedFrame = this.frame
      if (batch.state === 'failed' && performance.now() - batch.failedAt > FAIL_RETRY_MS) {
        batch.state = 'idle'
      }
      if (batch.state === 'ready') {
        drawn.push(batch)
        if (batch.atlasState === 'idle' && batch.hasSolid && distance < ATLAS_DISTANCE_M) {
          wanted.push({ batch, distance })
        }
      } else if (batch.state === 'idle') {
        wanted.push({ batch, distance })
      }
    }
    wanted.sort((a, b) => a.distance - b.distance) // nearest first
    for (const { batch } of wanted) {
      if (batch.state === 'idle') {
        if (loading < MAX_BATCH_LOADS) {
          this.requestBatch(batch)
          loading++
        }
      } else if (atlasLoading < MAX_ATLAS_LOADS) {
        this.requestAtlas(batch)
        atlasLoading++
      }
    }

    // ---- GL state envelope ----
    const prev = snapshot(gl2)
    let repaint = false
    try {
      gl2.pixelStorei(gl2.UNPACK_ALIGNMENT, 1)
      gl2.pixelStorei(gl2.UNPACK_FLIP_Y_WEBGL, false)
      gl2.pixelStorei(gl2.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false)
      gl2.bindBuffer(gl2.PIXEL_UNPACK_BUFFER, null)

      // render-time uploads of whatever the worker has finished. An atlas is
      // a multi-megabyte texture plus mipmaps: at most one per frame, and
      // never in a frame that also took geometry.
      let uploads = 0
      for (const batch of this.batches) {
        if (batch.pending) {
          if (uploads >= BATCH_UPLOADS_PER_FRAME) {
            repaint = true
            continue
          }
          try {
            this.upload(gl2, batch)
            if (batch.lastUsedFrame === this.frame) drawn.push(batch)
          } catch (error) {
            batch.pending = null
            batch.state = 'failed'
            batch.failedAt = performance.now()
            this.fail(error)
          }
          uploads++
        }
        if (batch.atlasPending) {
          if (uploads > 0) {
            repaint = true
            continue
          }
          this.uploadAtlas(gl2, batch)
          uploads = BATCH_UPLOADS_PER_FRAME
        }
      }
      if (this.collectPicks(gl2)) repaint = true
      if (this.sampleGround(drawn)) repaint = true
      this.publishLuts(gl2)
      if (!this.fallbackTex) {
        this.fallbackTex = gl2.createTexture()
        gl2.activeTexture(gl2.TEXTURE2)
        gl2.bindTexture(gl2.TEXTURE_2D, this.fallbackTex)
        gl2.texImage2D(gl2.TEXTURE_2D, 0, gl2.RGBA, 1, 1, 0, gl2.RGBA, gl2.UNSIGNED_BYTE,
          new Uint8Array([0, 0, 0, 0]))
      }

      if (drawn.length > 0 && this.stateTex && this.groundTex) {
        for (const batch of drawn) {
          const grid = batch.grid as NonNullable<Batch['grid']>
          const k = 1 / 65535
          batch.matrix.set(composeTRS(main,
            [ox + grid.min[0] * s, oy + grid.min[1] * s, grid.min[2] * s],
            [grid.extent[0] * k * s, grid.extent[1] * k * s, grid.extent[2] * k * s]))
        }
        this.draw(gl2, drawn)
        if (this.pickRequests.length) {
          this.resolvePicks(gl2, drawn, map)
          repaint = true // come back for the answer
        }
      } else {
        for (const request of this.pickRequests) request.resolve(null)
        this.pickRequests = []
      }
      this.evict(gl2)
    } finally {
      restore(gl2, prev)
    }
    this.stats.frames++
    this.stats.batchesDrawn = drawn.length
    this.stats.lastRenderMs = performance.now() - started
    if (repaint || loading > 0) map.triggerRepaint()
  }

  private bindCommon(gl: WebGL2RenderingContext): void {
    gl.useProgram(this.program)
    gl.uniform1i(this.uniforms.u_state, 0)
    gl.uniform1i(this.uniforms.u_ground, 1)
    gl.uniform1i(this.uniforms.u_aerial, 2)
    gl.activeTexture(gl.TEXTURE0)
    gl.bindTexture(gl.TEXTURE_2D, this.stateTex)
    gl.activeTexture(gl.TEXTURE1)
    gl.bindTexture(gl.TEXTURE_2D, this.groundTex)
    gl.activeTexture(gl.TEXTURE2)
    gl.enable(gl.DEPTH_TEST)
    gl.depthFunc(gl.LEQUAL)
    gl.disable(gl.CULL_FACE) // the source's winding is not consistent
  }

  private drawPass(gl: WebGL2RenderingContext, batches: Batch[], pass: number,
                   matrixOf: (batch: Batch) => Float32Array): void {
    gl.uniform1i(this.uniforms.u_pass, pass)
    for (const batch of batches) {
      const grid = batch.grid as NonNullable<Batch['grid']>
      gl.uniformMatrix4fv(this.uniforms.u_matrix, false, matrixOf(batch))
      gl.uniform1f(this.uniforms.u_gridPerMetreZ, 65535 / grid.extent[2])
      if (pass === PASS_SOLID) {
        gl.bindTexture(gl.TEXTURE_2D, batch.atlas ?? this.fallbackTex)
        gl.uniform1f(this.uniforms.u_hasAerial, batch.atlas ? 1 : 0)
      }
      gl.bindVertexArray(batch.vao)
      gl.drawElements(gl.TRIANGLES, batch.indexCount, gl.UNSIGNED_INT, 0)
      this.stats.drawCalls++
      if (pass !== PASS_PICK) this.stats.triangles += batch.indexCount / 3
    }
  }

  private draw(gl: WebGL2RenderingContext, drawn: Batch[]): void {
    this.bindCommon(gl)
    const own = (batch: Batch): Float32Array => batch.matrix

    // standing structures: opaque, depth-writing
    gl.disable(gl.BLEND)
    gl.depthMask(true)
    gl.colorMask(true, true, true, true)
    gl.disable(gl.POLYGON_OFFSET_FILL)
    this.drawPass(gl, drawn, PASS_SOLID, own)

    // destroyed structures: lay down nearest-surface depth first, then tint
    // once, so a shell reads as one even veil instead of stacked faces. Both
    // passes share the bias that lifts foundations clear of steep terrain.
    gl.enable(gl.POLYGON_OFFSET_FILL)
    gl.polygonOffset(this.bias.factor, this.bias.units)
    gl.colorMask(false, false, false, false)
    this.drawPass(gl, drawn, PASS_GHOST_DEPTH, own)
    gl.colorMask(true, true, true, true)
    gl.depthMask(false)
    gl.enable(gl.BLEND)
    gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA)
    this.drawPass(gl, drawn, PASS_GHOST_FILL, own)
    gl.disable(gl.POLYGON_OFFSET_FILL)

    // crease and silhouette edges for both kinds
    // silhouette and crease edges for both kinds: one instanced quad per
    // edge, blended over what was just drawn, hidden by nearer surfaces
    const edge = this.edgeUniforms
    const pixelRatio = gl.drawingBufferWidth / ((this.map as MLMap).getCanvas().clientWidth || gl.drawingBufferWidth)
    gl.useProgram(this.edgeProgram)
    gl.uniform1i(edge.u_state, 0)
    gl.uniform1i(edge.u_ground, 1)
    gl.uniform2f(edge.u_viewport, gl.drawingBufferWidth, gl.drawingBufferHeight)
    gl.uniform1f(edge.u_width, this.edgeWidth * pixelRatio)
    gl.uniform1f(edge.u_lineBias, this.bias.line)
    for (const batch of drawn) {
      const grid = batch.grid as NonNullable<Batch['grid']>
      gl.uniformMatrix4fv(edge.u_matrix, false, batch.matrix)
      gl.uniform1f(edge.u_gridPerMetreZ, 65535 / grid.extent[2])
      gl.bindVertexArray(batch.edgeVao)
      gl.drawArraysInstanced(gl.TRIANGLE_STRIP, 0, 4, batch.edgeCount)
      this.stats.drawCalls++
    }
    gl.depthMask(true)
  }

  /** Draw structure ids for the single pixel under each request and read it. */
  private resolvePicks(gl: WebGL2RenderingContext, drawn: Batch[], map: MLMap): void {
    const started = performance.now()
    if (!this.pickFbo) {
      this.pickFbo = gl.createFramebuffer()
      this.pickColor = gl.createTexture()
      this.pickDepth = gl.createRenderbuffer()
      gl.activeTexture(gl.TEXTURE2)
      gl.bindTexture(gl.TEXTURE_2D, this.pickColor)
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8, 1, 1, 0, gl.RGBA, gl.UNSIGNED_BYTE, null)
      nearest(gl)
      gl.bindRenderbuffer(gl.RENDERBUFFER, this.pickDepth)
      gl.renderbufferStorage(gl.RENDERBUFFER, gl.DEPTH_COMPONENT24, 1, 1)
      gl.bindFramebuffer(gl.FRAMEBUFFER, this.pickFbo)
      gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, this.pickColor, 0)
      gl.framebufferRenderbuffer(gl.FRAMEBUFFER, gl.DEPTH_ATTACHMENT, gl.RENDERBUFFER, this.pickDepth)
    }
    const canvas = map.getCanvas()
    const cssWidth = canvas.clientWidth || 1
    const cssHeight = canvas.clientHeight || 1
    const requests = this.pickRequests
    this.pickRequests = []
    this.bindCommon(gl)
    // the aerial sampler's unit must not hold the texture being rendered to
    gl.bindTexture(gl.TEXTURE_2D, this.fallbackTex)
    gl.uniform1f(this.uniforms.u_hasAerial, 0)
    gl.bindFramebuffer(gl.FRAMEBUFFER, this.pickFbo)
    gl.viewport(0, 0, 1, 1)
    gl.disable(gl.BLEND)
    gl.disable(gl.POLYGON_OFFSET_FILL)
    gl.disable(gl.SCISSOR_TEST)
    gl.depthMask(true)
    gl.colorMask(true, true, true, true)
    const scratch = new Float32Array(16)
    const zoomed = new Float64Array(16)
    for (const request of requests) {
      const ndcX = (2 * request.x) / cssWidth - 1
      const ndcY = 1 - (2 * request.y) / cssHeight
      // zoom clip space so the requested pixel fills the 1×1 target
      const zoom = (m: ArrayLike<number>, out: Float32Array | Float64Array): void => {
        for (let column = 0; column < 4; column++) {
          const w = m[column * 4 + 3]
          out[column * 4] = canvas.width * (m[column * 4] - ndcX * w)
          out[column * 4 + 1] = canvas.height * (m[column * 4 + 1] - ndcY * w)
          out[column * 4 + 2] = m[column * 4 + 2]
          out[column * 4 + 3] = w
        }
      }
      // only batches the pixel's own frustum passes through are drawn: one or
      // two, instead of everything on screen
      zoom(this.localMatrix, zoomed)
      const planes = extractFrustumPlanes(zoomed)
      const under = drawn.filter((batch) =>
        sphereInFrustum(planes, batch.cx, batch.cy, batch.cz, batch.radius))
      gl.clearColor(0, 0, 0, 0)
      gl.clearDepth(1)
      gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT)
      this.drawPass(gl, under, PASS_PICK, (batch) => {
        zoom(batch.matrix, scratch)
        return scratch
      })
      const buffer = gl.createBuffer()
      const sync = buffer && gl.fenceSync(gl.SYNC_GPU_COMMANDS_COMPLETE, 0)
      if (!buffer || !sync) {
        if (buffer) gl.deleteBuffer(buffer)
        request.resolve(null)
        continue
      }
      gl.bindBuffer(gl.PIXEL_PACK_BUFFER, buffer)
      gl.bufferData(gl.PIXEL_PACK_BUFFER, 4, gl.STREAM_READ)
      gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, 0)
      gl.bindBuffer(gl.PIXEL_PACK_BUFFER, null)
      this.pickReads.push({ buffer, sync, resolve: request.resolve })
    }
    gl.flush() // so the fences can signal without waiting for another draw
    this.stats.lastPickMs = performance.now() - started
  }

  /** Deliver id pixels whose GPU work has finished. True while some are outstanding. */
  private collectPicks(gl: WebGL2RenderingContext): boolean {
    if (this.pickReads.length === 0) return false
    const pixel = new Uint8Array(4)
    this.pickReads = this.pickReads.filter((read) => {
      const status = gl.clientWaitSync(read.sync, 0, 0)
      if (status === gl.TIMEOUT_EXPIRED) return true
      let id = 0
      if (status !== gl.WAIT_FAILED) {
        gl.bindBuffer(gl.PIXEL_PACK_BUFFER, read.buffer)
        gl.getBufferSubData(gl.PIXEL_PACK_BUFFER, 0, pixel)
        gl.bindBuffer(gl.PIXEL_PACK_BUFFER, null)
        id = pixel[0] | (pixel[1] << 8)
      }
      gl.deleteSync(read.sync)
      gl.deleteBuffer(read.buffer)
      read.resolve(id > 0 ? this.idToApn[id] || null : null)
      return false
    })
    return this.pickReads.length > 0
  }

  private evict(gl: WebGL2RenderingContext): void {
    if (this.stats.atlasBytes > ATLAS_BYTE_CAP) {
      const idle = this.batches
        .filter((b) => b.atlas && b.lastUsedFrame < this.frame - 120)
        .sort((a, b) => a.lastUsedFrame - b.lastUsedFrame)
      for (const batch of idle) {
        if (this.stats.atlasBytes <= ATLAS_BYTE_CAP * 0.8) break
        this.releaseAtlas(gl, batch)
      }
    }
    if (this.stats.geometryBytes > GEOMETRY_BYTE_CAP) {
      const idle = this.batches
        .filter((b) => b.state === 'ready' && b.lastUsedFrame < this.frame - 300)
        .sort((a, b) => a.lastUsedFrame - b.lastUsedFrame)
      for (const batch of idle) {
        if (this.stats.geometryBytes <= GEOMETRY_BYTE_CAP * 0.8) break
        this.release(gl, batch)
      }
    }
  }
}

function nearest(gl: WebGL2RenderingContext): void {
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST)
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST)
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE)
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE)
}

// MapLibre caches GL state and skips sets it believes are redundant, so the
// layer hands back exactly what it was given.
type Snapshot = ReturnType<typeof snapshot>

function snapshot(gl: WebGL2RenderingContext) {
  const activeTexture = gl.getParameter(gl.ACTIVE_TEXTURE) as number
  const textures: (WebGLTexture | null)[] = []
  for (let unit = 0; unit < 3; unit++) {
    gl.activeTexture(gl.TEXTURE0 + unit)
    textures.push(gl.getParameter(gl.TEXTURE_BINDING_2D) as WebGLTexture | null)
  }
  gl.activeTexture(activeTexture)
  return {
    activeTexture,
    textures,
    program: gl.getParameter(gl.CURRENT_PROGRAM) as WebGLProgram | null,
    vao: gl.getParameter(gl.VERTEX_ARRAY_BINDING) as WebGLVertexArrayObject | null,
    arrayBuffer: gl.getParameter(gl.ARRAY_BUFFER_BINDING) as WebGLBuffer | null,
    framebuffer: gl.getParameter(gl.FRAMEBUFFER_BINDING) as WebGLFramebuffer | null,
    renderbuffer: gl.getParameter(gl.RENDERBUFFER_BINDING) as WebGLRenderbuffer | null,
    viewport: gl.getParameter(gl.VIEWPORT) as Int32Array,
    blend: gl.isEnabled(gl.BLEND),
    blendSrcRgb: gl.getParameter(gl.BLEND_SRC_RGB) as number,
    blendDstRgb: gl.getParameter(gl.BLEND_DST_RGB) as number,
    blendSrcAlpha: gl.getParameter(gl.BLEND_SRC_ALPHA) as number,
    blendDstAlpha: gl.getParameter(gl.BLEND_DST_ALPHA) as number,
    depthTest: gl.isEnabled(gl.DEPTH_TEST),
    depthFunc: gl.getParameter(gl.DEPTH_FUNC) as number,
    depthMask: gl.getParameter(gl.DEPTH_WRITEMASK) as boolean,
    colorMask: gl.getParameter(gl.COLOR_WRITEMASK) as boolean[],
    cull: gl.isEnabled(gl.CULL_FACE),
    scissor: gl.isEnabled(gl.SCISSOR_TEST),
    polygonOffset: gl.isEnabled(gl.POLYGON_OFFSET_FILL),
    polygonOffsetFactor: gl.getParameter(gl.POLYGON_OFFSET_FACTOR) as number,
    polygonOffsetUnits: gl.getParameter(gl.POLYGON_OFFSET_UNITS) as number,
    clearColor: gl.getParameter(gl.COLOR_CLEAR_VALUE) as Float32Array,
    clearDepth: gl.getParameter(gl.DEPTH_CLEAR_VALUE) as number,
    unpackAlignment: gl.getParameter(gl.UNPACK_ALIGNMENT) as number,
    unpackFlipY: gl.getParameter(gl.UNPACK_FLIP_Y_WEBGL) as boolean,
    unpackPremultiply: gl.getParameter(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL) as boolean,
    unpackBuffer: gl.getParameter(gl.PIXEL_UNPACK_BUFFER_BINDING) as WebGLBuffer | null,
    packBuffer: gl.getParameter(gl.PIXEL_PACK_BUFFER_BINDING) as WebGLBuffer | null,
  }
}

function restore(gl: WebGL2RenderingContext, p: Snapshot): void {
  const toggle = (capability: number, on: boolean): void => {
    if (on) gl.enable(capability)
    else gl.disable(capability)
  }
  gl.bindVertexArray(p.vao)
  gl.bindBuffer(gl.ARRAY_BUFFER, p.arrayBuffer)
  gl.bindFramebuffer(gl.FRAMEBUFFER, p.framebuffer)
  gl.bindRenderbuffer(gl.RENDERBUFFER, p.renderbuffer)
  gl.viewport(p.viewport[0], p.viewport[1], p.viewport[2], p.viewport[3])
  for (let unit = 0; unit < 3; unit++) {
    gl.activeTexture(gl.TEXTURE0 + unit)
    gl.bindTexture(gl.TEXTURE_2D, p.textures[unit])
  }
  gl.activeTexture(p.activeTexture)
  gl.useProgram(p.program)
  toggle(gl.BLEND, p.blend)
  gl.blendFuncSeparate(p.blendSrcRgb, p.blendDstRgb, p.blendSrcAlpha, p.blendDstAlpha)
  toggle(gl.DEPTH_TEST, p.depthTest)
  gl.depthFunc(p.depthFunc)
  gl.depthMask(p.depthMask)
  gl.colorMask(p.colorMask[0], p.colorMask[1], p.colorMask[2], p.colorMask[3])
  toggle(gl.CULL_FACE, p.cull)
  toggle(gl.SCISSOR_TEST, p.scissor)
  toggle(gl.POLYGON_OFFSET_FILL, p.polygonOffset)
  gl.polygonOffset(p.polygonOffsetFactor, p.polygonOffsetUnits)
  gl.clearColor(p.clearColor[0], p.clearColor[1], p.clearColor[2], p.clearColor[3])
  gl.clearDepth(p.clearDepth)
  gl.pixelStorei(gl.UNPACK_ALIGNMENT, p.unpackAlignment)
  gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, p.unpackFlipY)
  gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, p.unpackPremultiply)
  gl.bindBuffer(gl.PIXEL_UNPACK_BUFFER, p.unpackBuffer)
  gl.bindBuffer(gl.PIXEL_PACK_BUFFER, p.packBuffer)
}
