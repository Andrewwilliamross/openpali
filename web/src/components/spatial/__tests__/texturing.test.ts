import { describe, expect, it } from 'vitest'
import { computeTileCover, lonLatToTileXY, zoomForNodeWidth } from '../texturing'

describe('mercator tile math', () => {
  it('matches the live-verified Wayback reference tile', () => {
    // Phase 2 research curl-verified this exact tile at the Palisades point:
    // lon -118.526, lat 34.045 → z18 x=44764, y=104678
    const t = lonLatToTileXY(-118.526, 34.045, 18)
    expect(Math.floor(t.x)).toBe(44764)
    expect(Math.floor(t.y)).toBe(104678)
  })

  it('tile y grows southward', () => {
    const north = lonLatToTileXY(-118.5, 34.1, 15)
    const south = lonLatToTileXY(-118.5, 34.0, 15)
    expect(south.y).toBeGreaterThan(north.y)
  })

  it('zoom shrinks for wider nodes and clamps to the service range', () => {
    const z127 = zoomForNodeWidth(127, 34.04)
    const z500 = zoomForNodeWidth(500, 34.04)
    const z8000 = zoomForNodeWidth(8000, 34.04)
    expect(z127).toBeGreaterThan(z500)
    expect(z500).toBeGreaterThan(z8000)
    expect(z127).toBeLessThanOrEqual(19)
    expect(zoomForNodeWidth(0.5, 34.04)).toBeLessThanOrEqual(19) // clamp high
    expect(zoomForNodeWidth(10_000_000, 34.04)).toBeGreaterThanOrEqual(12) // clamp low
  })
})

describe('tile cover', () => {
  it('a 127 m leaf node needs at most a 2×2 cover at its chosen zoom', () => {
    const lat = 34.0415
    const lon = -118.5285
    const halfDeg = 63.75 / 111_320 / Math.cos((lat * Math.PI) / 180)
    const halfLat = 63.75 / 110_574
    const zoom = zoomForNodeWidth(127.5, lat)
    const cover = computeTileCover(lon - halfDeg, lat - halfLat,
                                   lon + halfDeg, lat + halfLat, zoom)
    expect(cover.tiles.length).toBeGreaterThanOrEqual(1)
    expect(cover.tiles.length).toBeLessThanOrEqual(4)
  })

  it('mercator bbox is ordered and tight around the tiles', () => {
    const cover = computeTileCover(-118.53, 34.04, -118.526, 34.043, 17)
    expect(cover.mx1).toBeGreaterThan(cover.mx0)
    expect(cover.my1).toBeGreaterThan(cover.my0) // y down: south > north
    const n = 2 ** 17
    for (const t of cover.tiles) {
      // every cover tile must intersect the bbox
      expect(t.x / n).toBeLessThanOrEqual(cover.mx1)
      expect((t.x + 1) / n).toBeGreaterThanOrEqual(cover.mx0)
      expect(t.y / n).toBeLessThanOrEqual(cover.my1)
      expect((t.y + 1) / n).toBeGreaterThanOrEqual(cover.my0)
    }
  })

  it('a point-sized bbox still yields exactly one tile', () => {
    const cover = computeTileCover(-118.5285, 34.0415, -118.5285, 34.0415, 18)
    expect(cover.tiles.length).toBe(1)
  })
})
