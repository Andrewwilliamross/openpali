import { describe, expect, it } from 'vitest'
import type { MultiPolygon, Polygon } from 'geojson'
import { geometryAreaM2, largeParcelVisualWeight } from '../parcelPresentation'

const METERS_PER_DEGREE_AT_EQUATOR = (Math.PI / 180) * 6_371_008.8

function square(xM: number, yM: number, sizeM: number): [number, number][] {
  const x = xM / METERS_PER_DEGREE_AT_EQUATOR
  const y = yM / METERS_PER_DEGREE_AT_EQUATOR
  const size = sizeM / METERS_PER_DEGREE_AT_EQUATOR
  return [
    [x, y],
    [x + size, y],
    [x + size, y + size],
    [x, y + size],
    [x, y],
  ]
}

describe('geometryAreaM2', () => {
  it('estimates a Polygon area in square metres', () => {
    const polygon: Polygon = {
      type: 'Polygon',
      coordinates: [square(0, 0, 100)],
    }

    expect(geometryAreaM2(polygon)).toBeCloseTo(10_000, 4)
  })

  it('subtracts interior rings and sums MultiPolygon members', () => {
    const geometry: MultiPolygon = {
      type: 'MultiPolygon',
      coordinates: [
        [square(0, 0, 100), square(30, 30, 40)],
        [square(200, 0, 25)],
      ],
    }

    expect(geometryAreaM2(geometry)).toBeCloseTo(9_025, 4)
  })

  it('returns zero for malformed geometry rather than propagating NaN', () => {
    const malformed = {
      type: 'Polygon',
      coordinates: [[[Number.NaN, 0], [0, 1], [1, 1], [Number.NaN, 0]]],
    } as unknown as Polygon

    expect(geometryAreaM2(malformed)).toBe(0)
  })
})

describe('largeParcelVisualWeight', () => {
  it('keeps ordinary, invalid, and nonfinite areas at full strength', () => {
    expect(largeParcelVisualWeight(-1)).toBe(1)
    expect(largeParcelVisualWeight(0)).toBe(1)
    expect(largeParcelVisualWeight(20_000)).toBe(1)
    expect(largeParcelVisualWeight(Number.NaN)).toBe(1)
    expect(largeParcelVisualWeight(Number.POSITIVE_INFINITY)).toBe(1)
  })

  it('declines linearly from 1 at 20k m² to 0.35 at 100k m² and clamps there', () => {
    expect(largeParcelVisualWeight(60_000)).toBeCloseTo(0.675, 10)
    expect(largeParcelVisualWeight(100_000)).toBe(0.35)
    expect(largeParcelVisualWeight(500_000)).toBe(0.35)
  })
})
