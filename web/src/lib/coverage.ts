// coverage.json — the 3D honesty layer (ROADMAP D2).
// Per-APN geometry provenance emitted by the spatial export: which source the
// lot's 3D geometry comes from, how many splats it has, and when the source
// was acquired. The UI must label every rendered parcel so a placeholder can
// never masquerade as an observation.

export type GeometrySource = 'lariac_model' | 'footprint_extrusion' | 'parcel_prism'

export interface CoverageEntry {
  geometry_source: GeometrySource | null
  n_splats: number
  acquired: string | null
  missing_reason: string | null
}

export const GEOMETRY_SOURCE_LABELS: Record<GeometrySource, string> = {
  lariac_model: 'LARIAC 3D model (pre-fire)',
  footprint_extrusion: 'Footprint extrusion (approximate)',
  parcel_prism: 'Lot outline placeholder',
}

let cache: Promise<Record<string, CoverageEntry>> | null = null

export function fetchCoverage(): Promise<Record<string, CoverageEntry>> {
  if (!cache) {
    cache = fetch(`${import.meta.env.BASE_URL}data/coverage.json`)
      .then((r) => (r.ok ? (r.json() as Promise<Record<string, CoverageEntry>>) : {}))
      .catch(() => ({}))
  }
  return cache
}
