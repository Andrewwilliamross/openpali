// Read access to the release-pinned evidence API (`make evidence-api`).
import type { ParcelCollection } from './types'

export type Release = { release_id: string }

/** Ordered like the recovery ladder (openpali.domain.lifecycles.RECOVERY_STAGE); a pipeline test guards the order. `score` is that rung's position on the 0–100 ramp in colors.ts. */
export const stages:Record<string,{label:string;score:number}>={unknown:{label:'No recovery milestone established',score:0},cleanup:{label:'Cleanup reported complete',score:8},application:{label:'Rebuild application',score:15},design:{label:'Plans approved',score:30},permit:{label:'Permit issued',score:40},construction:{label:'Construction reported',score:60},construction_complete:{label:'Construction reported complete',score:92},occupancy:{label:'Occupancy certificate recorded',score:100}};

export function apiPath(release: string, tail: string): string {
  return `/v1/evidence/releases/${encodeURIComponent(release)}/${tail}`
}

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const r = await fetch(path, { signal })
  if (!r.ok) throw new Error(`Request failed (${r.status})`)
  return r.json() as Promise<T>
}

/** Parcels of the current evidence release, as served (no client-side joins). */
export async function fetchParcels(signal?: AbortSignal): Promise<ParcelCollection> {
  const release = await get<Release>('/v1/evidence/current', signal)
  return get<ParcelCollection>(apiPath(release.release_id, 'artifacts/parcels.geojson'), signal)
}
