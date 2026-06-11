// Pre-allocated GPU vertex-buffer pool with SIZE CLASSES.
//
// Panning across the canyons loads/evicts dozens of octree nodes per second;
// allocating a fresh VBO per node causes driver churn and main-thread stutter,
// so slots are pre-allocated once and recycled (acquire on load, release on
// evict — steady-state is allocation-free).
//
// Why classes: node payloads are heavily skewed (median ≈ 90 KB, leaves up to
// 448 KB). A single 448 KB slot size made GPU cost ≈ 3× the data and starved
// the residency cap into evict/reload thrash. Three classes keep slot waste
// under ~25% so the byte cap admits the true working set.

export interface PoolSlot {
  buffer: WebGLBuffer
  /** capacity in bytes (fixed per class) */
  capacity: number
  /** bytes valid in the current residency */
  used: number
  /** class index in SLOT_CLASSES */
  classIndex: number
}

export const SLOT_CLASSES = [64 * 1024, 192 * 1024, 448 * 1024] as const

/** Smallest class that fits `bytes`, or -1 when nothing fits (oversize path). */
export function chooseSlotClass(bytes: number,
                                classes: readonly number[] = SLOT_CLASSES): number {
  for (let i = 0; i < classes.length; i++) {
    if (bytes <= classes[i]) return i
  }
  return -1
}

export class BufferPool {
  private gl: WebGL2RenderingContext
  private free: PoolSlot[][] = SLOT_CLASSES.map(() => [])
  private all: PoolSlot[] = []
  private bank: number

  /** total bytes resident in pooled GPU memory (capacity, not used) */
  get capacityBytes(): number {
    return this.all.reduce((s, slot) => s + slot.capacity, 0)
  }

  get freeCount(): number {
    return this.free.reduce((s, f) => s + f.length, 0)
  }

  get totalCount(): number {
    return this.all.length
  }

  constructor(gl: WebGL2RenderingContext, initialPerClass = 16, bank = 8) {
    this.gl = gl
    this.bank = bank
    for (let c = 0; c < SLOT_CLASSES.length; c++) this.grow(c, initialPerClass)
  }

  private grow(classIndex: number, n: number): void {
    const gl = this.gl
    const capacity = SLOT_CLASSES[classIndex]
    for (let i = 0; i < n; i++) {
      const buffer = gl.createBuffer()
      if (!buffer) throw new Error('BufferPool: createBuffer failed')
      gl.bindBuffer(gl.ARRAY_BUFFER, buffer)
      // allocate once; all future writes are bufferSubData into this block
      gl.bufferData(gl.ARRAY_BUFFER, capacity, gl.DYNAMIC_DRAW)
      const slot: PoolSlot = { buffer, capacity, used: 0, classIndex }
      this.all.push(slot)
      this.free[classIndex].push(slot)
    }
    gl.bindBuffer(gl.ARRAY_BUFFER, null)
  }

  /** Acquire the smallest-fitting slot and upload `data` into it. */
  acquire(data: ArrayBufferView): PoolSlot {
    const classIndex = chooseSlotClass(data.byteLength)
    if (classIndex < 0) {
      throw new Error(
        `BufferPool: payload ${data.byteLength}B exceeds the largest class`)
    }
    if (this.free[classIndex].length === 0) this.grow(classIndex, this.bank)
    const slot = this.free[classIndex].pop() as PoolSlot
    const gl = this.gl
    gl.bindBuffer(gl.ARRAY_BUFFER, slot.buffer)
    gl.bufferSubData(gl.ARRAY_BUFFER, 0, data)
    gl.bindBuffer(gl.ARRAY_BUFFER, null)
    slot.used = data.byteLength
    return slot
  }

  /** Overwrite a held slot in place (used by the depth re-sorter). */
  rewrite(slot: PoolSlot, data: ArrayBufferView): void {
    if (data.byteLength > slot.capacity) {
      throw new Error('BufferPool.rewrite: payload exceeds slot capacity')
    }
    const gl = this.gl
    gl.bindBuffer(gl.ARRAY_BUFFER, slot.buffer)
    gl.bufferSubData(gl.ARRAY_BUFFER, 0, data)
    gl.bindBuffer(gl.ARRAY_BUFFER, null)
    slot.used = data.byteLength
  }

  /** Return a slot to its class's free list (GPU memory retained for reuse). */
  release(slot: PoolSlot): void {
    slot.used = 0
    this.free[slot.classIndex].push(slot)
  }

  /** Delete all GPU buffers (layer teardown only). */
  destroy(): void {
    for (const s of this.all) this.gl.deleteBuffer(s.buffer)
    this.all = []
    this.free = SLOT_CLASSES.map(() => [])
  }
}
