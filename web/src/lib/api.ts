// Read access to the release-pinned evidence API (`make evidence-api`).
import type { MapData, ParcelRow } from './types'

function apiPath(release: string, tail: string): string {
  return `/v1/evidence/releases/${encodeURIComponent(release)}/${tail}`
}

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const r = await fetch(path, { signal })
  if (!r.ok) throw new Error(`Request failed (${r.status})`)
  return r.json() as Promise<T>
}

interface IndexArtifact {
  fields: string[]
  rows: (string | number | null)[][]
}

/**
 * What the map needs from the current release: the URL of the parcel polygons
 * (MapLibre fetches and parses those in its worker) and the compact parcel
 * index that drives search, neighborhood framing and structure colours.
 * Both are pinned to one release id, so they always describe the same data.
 */
export async function fetchMapData(signal?: AbortSignal): Promise<MapData> {
  const { release_id: release } = await get<{ release_id: string }>('/v1/evidence/current', signal)
  const index = await get<IndexArtifact>(apiPath(release, 'artifacts/parcel-index.json'), signal)
  const column = (name: string): number => {
    const i = index.fields.indexOf(name)
    if (i < 0) throw new Error(`parcel index has no "${name}" column; rebuild the release`)
    return i
  }
  const [apn, address, lon, lat, damage, score] =
    ['apn', 'address', 'lon', 'lat', 'damage', 'score'].map(column)
  const parcels: ParcelRow[] = index.rows.map((row) => ({
    apn: row[apn] as string,
    address: (row[address] as string) ?? '',
    center: row[lon] === null ? null : [row[lon] as number, row[lat] as number],
    destroyed: row[damage] === 'destroyed',
    score: row[score] as number | null,
  }))
  return { parcelsUrl: apiPath(release, 'artifacts/parcels.geojson'), parcels }
}
