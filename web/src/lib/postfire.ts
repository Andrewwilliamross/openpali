// Release-pinned post-fire spatial source discovery (SPATIAL-001).
//
// The client resolves the current release once, reads its spatial-asset
// selection, and derives release-qualified asset URLs. Everything about the
// source — acquisition date (the 2025 flight, never our processing time),
// observation kind, rights state, coverage — comes from the release manifest,
// so the renderer and UI can never show a stale or unselected asset version.

export interface PostfireAsset {
  asset_id: string
  version_id: string
  asset_kind: string
  vintage_slot: string
  observation_kind: string
  rights_state: string
  acquisition_start: string | null
  acquisition_end: string | null
  processed_at: string | null
  resolution_m: number | null
  coverage: Record<string, unknown>
  quality: Record<string, unknown>
}

export interface PostfireSources {
  releaseId: string
  surfel: PostfireAsset | null
  terrain: PostfireAsset | null
  surfelBase: string | null
  terrainTileUrl: string | null
}

const API_BASE = '/v1'

let sourcesPromise: Promise<PostfireSources | null> | null = null

export function fetchPostfireSources(): Promise<PostfireSources | null> {
  sourcesPromise ??= (async () => {
    try {
      // generated, contract-checked client (BACKEND-001): the shapes here are
      // regenerated from contracts/openapi.json, which check-fast diffs
      // against the live app schema
      const { resolveCurrentV1ReleasesCurrentGet, spatialAssetsV1ReleasesReleaseIdSpatialAssetsGet } =
        await import('../api/generated/sdk.gen')
      const releaseResp = await resolveCurrentV1ReleasesCurrentGet()
      if (!releaseResp.data) return null
      const release = releaseResp.data as { release_id: string }
      const assetsResp = await spatialAssetsV1ReleasesReleaseIdSpatialAssetsGet({
        path: { release_id: release.release_id },
      })
      if (!assetsResp.data) return null
      const spatial = assetsResp.data as unknown as { assets: PostfireAsset[] }
      const find = (id: string): PostfireAsset | null =>
        spatial.assets.find((a) => a.asset_id === id) ?? null
      const surfel = find('usgs-surfel-aoi')
      const terrain = find('usgs-terrain-aoi')
      const base = (a: PostfireAsset): string =>
        `${API_BASE}/releases/${release.release_id}/spatial/${a.asset_id}/${a.version_id}`
      return {
        releaseId: release.release_id,
        surfel,
        terrain,
        surfelBase: surfel ? base(surfel) : null,
        terrainTileUrl: terrain ? `${base(terrain)}/{z}/{x}/{y}.png` : null,
      }
    } catch {
      return null // API unreachable (static/dev hosting) — post-fire layer absent
    }
  })()
  return sourcesPromise
}

// ---- per-parcel post-fire coverage (from the asset's picking index) --------

interface PickEntryLite {
  n: number
}

let pickingPromise: Promise<Record<string, PickEntryLite> | null> | null = null

export function fetchPostfirePicking(): Promise<Record<string, PickEntryLite> | null> {
  pickingPromise ??= (async () => {
    const sources = await fetchPostfireSources()
    if (!sources?.surfelBase) return null
    try {
      const resp = await fetch(`${sources.surfelBase}/picking.json`)
      if (!resp.ok) return null
      return (await resp.json()) as Record<string, PickEntryLite>
    } catch {
      return null
    }
  })()
  return pickingPromise
}

/** Human label for the post-fire surface source, from manifest facts only. */
export function postfireSourceLabel(asset: PostfireAsset): string {
  const acquired = asset.acquisition_start?.slice(0, 10) ?? 'unknown date'
  return `USGS post-fire lidar bare earth (flown ${acquired}, preliminary)`
}
