/// <reference lib="webworker" />
// Fetches and prepares building batches off the main thread: network, format
// adaptation, edge extraction and roof-image decoding all happen here, and
// the results cross back as transferables. The main thread only uploads.
import {
  creaseEdges,
  EDGE_BYTES,
  edgeInstances,
  quantizeV1,
  structureBases,
  type DecodedBatch,
  type QuantizedGrid,
  type SceneNode,
} from './format'

export type WorkerRequest =
  | { kind: 'batch'; requestId: number; baseUrl: string; schema: string; node: SceneNode }
  | { kind: 'atlas'; requestId: number; url: string }
  | { kind: 'cancel'; requestId: number }

export type WorkerResponse =
  | { kind: 'batch'; requestId: number; batch: DecodedBatch }
  | { kind: 'atlas'; requestId: number; image: ImageBitmap }
  | { kind: 'error'; requestId: number; message: string }

const controllers = new Map<number, AbortController>()

async function bytes(url: string, expected: number, signal: AbortSignal): Promise<ArrayBuffer> {
  const response = await fetch(url, { signal })
  if (!response.ok) throw new Error(`${url}: HTTP ${response.status}`)
  const buffer = await response.arrayBuffer()
  // a static host that answers a missing file with its index page must not
  // reach the GPU as geometry
  if (buffer.byteLength !== expected) {
    throw new Error(`${url}: ${buffer.byteLength} bytes, manifest says ${expected}`)
  }
  return buffer
}

async function loadBatch(baseUrl: string, schema: string, node: SceneNode,
                         signal: AbortSignal): Promise<DecodedBatch> {
  const [vertexBytes, indexBytes] = await Promise.all([
    bytes(`${baseUrl}/${node.id}.vertices.bin`, node.vertex_bytes, signal),
    bytes(`${baseUrl}/${node.id}.indices.bin`, node.index_bytes, signal),
  ])
  // stored narrow where a batch allows it; one width on the GPU keeps a single draw path
  const indices = node.index_type === 'u16'
    ? Uint32Array.from(new Uint16Array(indexBytes))
    : new Uint32Array(indexBytes)
  let vertices: ArrayBuffer
  let vertexCount: number
  let grid: QuantizedGrid
  if (schema === 'openpali-scene-v2') {
    if (!node.grid) throw new Error(`batch ${node.id}: v2 node without a grid`)
    vertices = vertexBytes
    vertexCount = node.vertex_count
    grid = node.grid
  } else {
    ({ vertices, vertexCount, grid } = quantizeV1(new Float32Array(vertexBytes)))
  }
  const edges = edgeInstances(vertices, creaseEdges(vertices, indices, grid))
  return {
    id: node.id,
    grid,
    vertices,
    vertexCount,
    indices,
    edges,
    edgeCount: edges.byteLength / EDGE_BYTES,
    bases: structureBases(vertices, grid),
  }
}

/** The build's stitched aerial image of the batch's uv rectangle. */
async function loadAtlas(url: string, signal: AbortSignal): Promise<ImageBitmap> {
  const response = await fetch(url, { signal })
  if (!response.ok) throw new Error(`${url}: HTTP ${response.status}`)
  return createImageBitmap(await response.blob())
}

self.onmessage = (event: MessageEvent<WorkerRequest>) => {
  const request = event.data
  if (request.kind === 'cancel') {
    controllers.get(request.requestId)?.abort()
    return
  }
  const controller = new AbortController()
  controllers.set(request.requestId, controller)
  const post = (message: WorkerResponse, transfer: Transferable[] = []): void =>
    (self as DedicatedWorkerGlobalScope).postMessage(message, transfer)
  const work = request.kind === 'batch'
    ? loadBatch(request.baseUrl, request.schema, request.node, controller.signal).then((batch) =>
        post({ kind: 'batch', requestId: request.requestId, batch },
          [batch.vertices, batch.indices.buffer, batch.edges, batch.bases.buffer]))
    : loadAtlas(request.url, controller.signal).then((image) =>
        post({ kind: 'atlas', requestId: request.requestId, image }, [image]))
  work
    .catch((error: unknown) => {
      post({
        kind: 'error',
        requestId: request.requestId,
        message: error instanceof Error ? error.message : String(error),
      })
    })
    .finally(() => controllers.delete(request.requestId))
}
