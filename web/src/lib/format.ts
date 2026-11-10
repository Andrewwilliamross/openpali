import type { Polygon, MultiPolygon } from 'geojson'

export function titleCase(s: string): string {
  return s
    .toLowerCase()
    .replace(/\b([a-z])/g, (m) => m.toUpperCase())
    .replace(/\b(Dr|St|Ave|Blvd|Pl|Ln|Rd|Ct|Way|Ter)\b\.?/gi, (m) => m)
}

/** Quick centroid: average of outer-ring vertices (fine for parcel-sized polygons). */
export function centroid(geom: Polygon | MultiPolygon): [number, number] {
  const ring =
    geom.type === 'Polygon' ? geom.coordinates[0] : geom.coordinates[0][0]
  let x = 0
  let y = 0
  for (const [lx, ly] of ring) {
    x += lx
    y += ly
  }
  return [x / ring.length, y / ring.length]
}

/** 0 when the user asks for reduced motion (WCAG 2.3.3), else the given ms. */
export function motionMs(ms: number): number {
  if (typeof window !== 'undefined'
      && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
    return 0
  }
  return ms
}
