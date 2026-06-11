// Pre-allocated GPU vertex-buffer pool.
//
// Panning across the canyons loads/evicts dozens of octree nodes per second;
// allocating a fresh VBO per node (and letting GC + driver churn reclaim them)
// causes main-thread stutter. Instead we pre-allocate fixed-size buffer slots
// once and recycle them: acquire on node load, release on evict. Slots are
// sized to the largest leaf payload; the pool grows by whole banks only when
// genuinely exhausted (and never shrinks — steady-state is allocation-free).

export interface PoolSlot {
  buffer: WebGLBuffer
  /** capacity in bytes (fixed at pool construction) */
  capacity: number
  /** bytes valid in the current residency */
  used: number
  /** pool bookkeeping */
  index: number
}

export class BufferPool {
  private gl: WebGL2RenderingContext
  private slotBytes: number
  private free: PoolSlot[] = []
  private all: PoolSlot[] = []
  private bank: number

  /** total bytes resident in pooled GPU memory (capacity, not used) */
  get capacityBytes(): number {
    return this.all.length * this.slotBytes
  }

  get freeCount(): number {
    return this.free.length
  }

  get totalCount(): number {
    return this.all.length
  }

  constructor(gl: WebGL2RenderingContext, slotBytes: number, initialSlots = 64,
              bank = 16) {
    this.gl = gl
    this.slotBytes = slotBytes
    this.bank = bank
    this.grow(initialSlots)
  }

  private grow(n: number): void {
    const gl = this.gl
    for (let i = 0; i < n; i++) {
      const buffer = gl.createBuffer()
      if (!buffer) throw new Error('BufferPool: createBuffer failed')
      gl.bindBuffer(gl.ARRAY_BUFFER, buffer)
      // allocate once; all future writes are bufferSubData into this block
      gl.bufferData(gl.ARRAY_BUFFER, this.slotBytes, gl.DYNAMIC_DRAW)
      const slot: PoolSlot = { buffer, capacity: this.slotBytes, used: 0,
                               index: this.all.length }
      this.all.push(slot)
      this.free.push(slot)
    }
    gl.bindBuffer(gl.ARRAY_BUFFER, null)
  }

  /** Acquire a slot and upload `data` into it. Grows by one bank if empty. */
  acquire(data: ArrayBufferView): PoolSlot {
    if (data.byteLength > this.slotBytes) {
      throw new Error(
        `BufferPool: payload ${data.byteLength}B exceeds slot ${this.slotBytes}B`)
    }
    if (this.free.length === 0) this.grow(this.bank)
    const slot = this.free.pop() as PoolSlot
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

  /** Return a slot to the free list. The GPU memory is retained for reuse. */
  release(slot: PoolSlot): void {
    slot.used = 0
    this.free.push(slot)
  }

  /** Delete all GPU buffers (layer teardown only). */
  destroy(): void {
    for (const s of this.all) this.gl.deleteBuffer(s.buffer)
    this.all = []
    this.free = []
  }
}
