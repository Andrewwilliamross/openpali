import type { MultiPolygon, Polygon, Position } from 'geojson'

const EARTH_RADIUS_M = 6_371_008.8
const DEG_TO_RAD = Math.PI / 180
const NORMAL_AREA_M2 = 20_000
const LARGE_AREA_M2 = 100_000
const MIN_VISUAL_WEIGHT = 0.35

type ParcelGeometry = Polygon | MultiPolygon

interface LocalProjection {
  lon: number
  lat: number
  cosLat: number
}

/**
 * Estimates a parcel geometry's area in square metres using a local
 * equirectangular projection. It is accurate for parcel-sized geometry and
 * deliberately returns 0 for malformed or empty input so presentation code
 * can leave the feature at its normal visual weight.
 */
export function geometryAreaM2(geometry: ParcelGeometry): number {
  const projection = localProjection(geometry)
  if (!projection) return 0

  const polygons = geometry.type === 'Polygon' ? [geometry.coordinates] : geometry.coordinates
  let total = 0

  for (const polygon of polygons) {
    if (!Array.isArray(polygon) || polygon.length === 0) continue
    const outer = ringAreaM2(polygon[0], projection)
    if (outer === 0) continue

    const holes = polygon
      .slice(1)
      .reduce((sum, ring) => sum + ringAreaM2(ring, projection), 0)
    total += Math.max(0, outer - holes)
  }

  return Number.isFinite(total) && total >= 0 ? total : 0
}

/**
 * Keeps ordinary parcels at full visual strength, then smoothly attenuates
 * unusually large valid parcels. Invalid input deliberately preserves the
 * normal weight rather than making a feature disappear.
 */
export function largeParcelVisualWeight(areaM2: number): number {
  if (!Number.isFinite(areaM2) || areaM2 <= NORMAL_AREA_M2) return 1
  if (areaM2 >= LARGE_AREA_M2) return MIN_VISUAL_WEIGHT

  const progress = (areaM2 - NORMAL_AREA_M2) / (LARGE_AREA_M2 - NORMAL_AREA_M2)
  return 1 - progress * (1 - MIN_VISUAL_WEIGHT)
}

function localProjection(geometry: ParcelGeometry): LocalProjection | null {
  const positions = positionsFor(geometry)
  if (positions.length === 0) return null

  const [lon, lat] = positions[0]
  const referenceLat = positions.reduce((sum, [, y]) => sum + y, 0) / positions.length
  const cosLat = Math.cos(referenceLat * DEG_TO_RAD)
  if (!Number.isFinite(cosLat) || cosLat <= 0) return null

  return { lon, lat, cosLat }
}

function positionsFor(geometry: ParcelGeometry): [number, number][] {
  const positions: [number, number][] = []
  const polygons = geometry.type === 'Polygon' ? [geometry.coordinates] : geometry.coordinates

  for (const polygon of polygons) {
    if (!Array.isArray(polygon)) continue
    for (const ring of polygon) {
      if (!Array.isArray(ring)) continue
      for (const position of ring) {
        if (isPosition(position)) positions.push([position[0], position[1]])
      }
    }
  }

  return positions
}

function ringAreaM2(ring: Position[] | undefined, projection: LocalProjection): number {
  if (!Array.isArray(ring)) return 0

  const positions = ring.filter(isPosition)
  if (positions.length < 3) return 0

  let twiceArea = 0
  for (let i = 0; i < positions.length; i++) {
    const [lonA, latA] = positions[i]
    const [lonB, latB] = positions[(i + 1) % positions.length]
    const [xA, yA] = project(lonA, latA, projection)
    const [xB, yB] = project(lonB, latB, projection)
    twiceArea += xA * yB - xB * yA
  }

  const area = Math.abs(twiceArea) / 2
  return Number.isFinite(area) ? area : 0
}

function project(lon: number, lat: number, projection: LocalProjection): [number, number] {
  const deltaLon = wrappedLongitudeDelta(lon - projection.lon)
  return [
    deltaLon * DEG_TO_RAD * EARTH_RADIUS_M * projection.cosLat,
    (lat - projection.lat) * DEG_TO_RAD * EARTH_RADIUS_M,
  ]
}

function wrappedLongitudeDelta(delta: number): number {
  return ((delta + 540) % 360) - 180
}

function isPosition(value: unknown): value is Position {
  return (
    Array.isArray(value) &&
    value.length >= 2 &&
    typeof value[0] === 'number' &&
    typeof value[1] === 'number' &&
    Number.isFinite(value[0]) &&
    Number.isFinite(value[1]) &&
    value[0] >= -180 &&
    value[0] <= 180 &&
    value[1] >= -90 &&
    value[1] <= 90
  )
}
