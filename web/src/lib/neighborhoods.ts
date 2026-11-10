// Pacific Palisades sub-neighborhoods: community names with approximate
// centres, not legal boundaries. Mirrors pipeline/palisades/neighborhoods.py,
// including its nearest-centre assignment.
import type { ParcelRow } from './types'

export interface Neighborhood {
  name: string
  center: [number, number]
  /** fallback zoom when no scored parcel is assigned to the neighborhood */
  zoom: number
}

export const NEIGHBORHOODS: Neighborhood[] = [
  { name: 'The Alphabets / Village', center: [-118.5266, 34.044], zoom: 15.5 },
  { name: 'Huntington Palisades', center: [-118.519, 34.0368], zoom: 15.3 },
  { name: 'El Medio Bluffs', center: [-118.545, 34.0405], zoom: 15.3 },
  { name: 'Marquez Knolls', center: [-118.552, 34.048], zoom: 15.2 },
  { name: 'Castellammare', center: [-118.557, 34.044], zoom: 15.5 },
  { name: 'Paseo Miramar / Castellammare Mesa', center: [-118.553, 34.0512], zoom: 15.3 },
  { name: 'Palisades Highlands', center: [-118.543, 34.078], zoom: 14.6 },
  { name: 'Bienveneda / Temescal', center: [-118.539, 34.056], zoom: 15.0 },
  { name: 'Rustic Canyon', center: [-118.512, 34.04], zoom: 15.2 },
  { name: 'Santa Monica Canyon', center: [-118.5085, 34.033], zoom: 15.4 },
  { name: 'The Riviera', center: [-118.501, 34.0455], zoom: 15.0 },
  { name: 'Sunset Mesa (County)', center: [-118.566, 34.042], zoom: 15.2 },
  { name: 'Topanga (County)', center: [-118.588, 34.07], zoom: 13.8 },
  { name: 'Malibu — Las Flores / PCH', center: [-118.63, 34.037], zoom: 14.2 },
]

export function nearestNeighborhood(lon: number, lat: number): string {
  const cos = Math.cos((lat * Math.PI) / 180)
  let best = ''
  let bestD = Infinity
  for (const n of NEIGHBORHOODS) {
    const d = ((lon - n.center[0]) * cos) ** 2 + (lat - n.center[1]) ** 2
    if (d < bestD) {
      best = n.name
      bestD = d
    }
  }
  return best
}

export type Bounds = [[number, number], [number, number]]

/**
 * The view for each neighborhood: the extent of the parcels assigned to it.
 * The middle 80% of centroids in each axis frames the built-up core: nearest-
 * centre assignment also hands a neighborhood its outlying canyon parcels,
 * and the full extent would zoom the camera out past the streets.
 */
export function neighborhoodBounds(parcels: ParcelRow[]): Map<string, Bounds> {
  const groups = new Map<string, { lon: number[]; lat: number[] }>()
  for (const parcel of parcels) {
    if (!parcel.center) continue
    const [lon, lat] = parcel.center
    const name = nearestNeighborhood(lon, lat)
    const g = groups.get(name) ?? { lon: [], lat: [] }
    g.lon.push(lon)
    g.lat.push(lat)
    groups.set(name, g)
  }
  const out = new Map<string, Bounds>()
  for (const [name, g] of groups) {
    if (g.lon.length < 5) continue // too few to describe an extent
    g.lon.sort((a, b) => a - b)
    g.lat.sort((a, b) => a - b)
    const lo = Math.floor(g.lon.length * 0.1)
    const hi = g.lon.length - 1 - lo
    out.set(name, [[g.lon[lo], g.lat[lo]], [g.lon[hi], g.lat[hi]]])
  }
  return out
}
