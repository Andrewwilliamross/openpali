import { describe, expect, it } from 'vitest'
import { mirrored } from '../imageryProtocol'

describe('mirrored', () => {
  const has = mirrored({ tiles: '', maxzoom: 20, cover_zoom: 18, cover: [[40, 80]] })

  it('holds the cover tile, its descendants to maxzoom, and its ancestors', () => {
    expect(has(18, 40, 80)).toBe(true)
    expect(has(20, 163, 323)).toBe(true)
    expect(has(17, 20, 40)).toBe(true)
    expect(has(11, 0, 0)).toBe(true)
  })

  it('leaves everything else to the vendor', () => {
    expect(has(18, 41, 80)).toBe(false)
    expect(has(20, 164, 323)).toBe(false)
    expect(has(21, 320, 640)).toBe(false)
  })
})
