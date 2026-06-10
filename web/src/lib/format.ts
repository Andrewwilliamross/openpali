export function titleCase(s: string): string {
  return s
    .toLowerCase()
    .replace(/\b([a-z])/g, (m) => m.toUpperCase())
    .replace(/\b(Dr|St|Ave|Blvd|Pl|Ln|Rd|Ct|Way|Ter)\b\.?/gi, (m) => m)
}

export function fmtNumber(n: number): string {
  return n.toLocaleString('en-US')
}

export function fmtPct(part: number, whole: number): string {
  if (!whole) return '–'
  return `${Math.round((part / whole) * 100)}%`
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '–'
  const d = new Date(iso + (iso.length === 10 ? 'T12:00:00' : ''))
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

export function fmtMoney(n: number | null): string {
  if (n == null) return '–'
  return n >= 1_000_000
    ? `$${(n / 1_000_000).toFixed(1)}M`
    : `$${Math.round(n / 1000)}k`
}

export function daysAgo(iso: string | null): string {
  if (!iso) return ''
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000)
  if (days < 1) return 'today'
  if (days === 1) return 'yesterday'
  if (days < 60) return `${days} days ago`
  return `${Math.round(days / 30.4)} months ago`
}

import type { Polygon, MultiPolygon } from 'geojson'

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
