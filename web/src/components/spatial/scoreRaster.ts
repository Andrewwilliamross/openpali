// Top-down raster of the current per-parcel score colours, in the splat
// tileset's local ENU frame. The splat vertex shader samples it at each splat
// centre, so 3D structures take the SAME live colour as the draped parcel
// fills instead of whatever tint was baked into the tiles at export time.
//
// CPU-only (2D canvas): the render layer uploads the result at render time.
import type { MultiPolygon, Polygon } from 'geojson'

export interface ScoredShape {
  geometry: Polygon | MultiPolygon
  /** CSS colour for this parcel's score */
  color: string
}

export interface ScoreRaster {
  image: TexImageSource
  /** [west edge X, NORTH edge Y] in ENU metres */
  originEnu: [number, number]
  /** [1/widthM, 1/heightM] */
  invSizeEnu: [number, number]
  width: number
  height: number
}

const METERS_PER_DEG_LAT = 110_574
const METERS_PER_DEG_LON_EQ = 111_320

/** Pixel dimensions for an ENU rectangle whose longest side is `maxPx`. */
export function rasterSize(widthM: number, heightM: number, maxPx: number): [number, number] {
  const scale = maxPx / Math.max(widthM, heightM)
  return [Math.max(1, Math.round(widthM * scale)), Math.max(1, Math.round(heightM * scale))]
}

/** lon/lat → raster pixel, using the render layer's ENU linearisation. */
export function projector(rect: [number, number, number, number],
                          origin: { lon: number; lat: number },
                          width: number, height: number,
                          ): (lon: number, lat: number) => [number, number] {
  const [minX, minY, maxX, maxY] = rect
  const mPerLon = METERS_PER_DEG_LON_EQ * Math.cos((origin.lat * Math.PI) / 180)
  const sx = width / (maxX - minX)
  const sy = height / (maxY - minY)
  return (lon, lat) => [
    ((lon - origin.lon) * mPerLon - minX) * sx,
    (maxY - (lat - origin.lat) * METERS_PER_DEG_LAT) * sy, // row 0 = north
  ]
}

export function rasterizeScores(shapes: ScoredShape[],
                                rect: [number, number, number, number],
                                origin: { lon: number; lat: number },
                                maxPx: number): ScoreRaster | null {
  const [minX, minY, maxX, maxY] = rect
  const [width, height] = rasterSize(maxX - minX, maxY - minY, maxPx)
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext('2d')
  if (!ctx) return null
  const project = projector(rect, origin, width, height)
  for (const { geometry, color } of shapes) {
    const polygons = geometry.type === 'Polygon' ? [geometry.coordinates] : geometry.coordinates
    ctx.beginPath()
    for (const polygon of polygons) {
      for (const ring of polygon) {
        ring.forEach(([lon, lat], i) => {
          const [x, y] = project(lon, lat)
          if (i === 0) ctx.moveTo(x, y)
          else ctx.lineTo(x, y)
        })
        ctx.closePath()
      }
    }
    ctx.fillStyle = color
    ctx.fill('evenodd')
  }
  return {
    image: canvas,
    originEnu: [minX, maxY],
    invSizeEnu: [1 / (maxX - minX), 1 / (maxY - minY)],
    width,
    height,
  }
}
