// Terrain source resolution for the 3D map.
//
// The terrain DEM is config-driven rather than hardcoded so the post-fire
// LiDAR DTM can be swapped in behind a feature flag without touching MapView.
// Default (flag off) is the global AWS Open Data Mapzen terrarium DEM — exactly
// the prior behavior. With the flag on AND a tiles URL configured, the in-footprint
// post-fire DTM is used instead.
//
// The post-fire tiles are produced offline (pipeline/core/spatial/postfire_dem.py):
// the USGS 3DEP / OpenTopography DTM, reprojected to WebMercator and lifted
// NAVD88/GEOID18 -> WGS84 ellipsoidal at ingestion so it shares the splat store's
// vertical frame (no client-side geoid math). They live in object storage, not git.

export type DemEncoding = 'terrarium' | 'mapbox' | 'custom'

export interface TerrainConfig {
  tiles: string
  encoding: DemEncoding
  tileSize: number
  minzoom: number
  maxzoom: number
  bounds?: [number, number, number, number]
  attribution: string
  /** vertical datum the tiles were baked to — provenance for debug/QA */
  vdatum?: string
}

// Global fallback terrain. maxzoom 15 is mandatory — z16 does not exist upstream
// and must overzoom, not 404.
export const AWS_TERRARIUM: TerrainConfig = {
  tiles: 'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png',
  encoding: 'terrarium',
  tileSize: 256,
  minzoom: 0,
  maxzoom: 15,
  attribution: 'Terrain: USGS 3DEP/SRTM via Mapzen terrain tiles (AWS Open Data)',
}

// Palisades post-fire DEM footprint (WGS84), from OTSDEM.012025.6340.2. Outside
// these bounds the post-fire terrain is undefined; the camera stays in-footprint.
export const POSTFIRE_DTM_BOUNDS: [number, number, number, number] =
  [-118.698, 34.027, -118.431, 34.139]

export interface TerrainEnv {
  VITE_POSTFIRE_TERRAIN?: string
  VITE_POSTFIRE_TERRAIN_URL?: string
  VITE_POSTFIRE_TERRAIN_ENCODING?: string
  VITE_POSTFIRE_TERRAIN_MAXZOOM?: string
  [k: string]: unknown
}

function currentEnv(): TerrainEnv {
  return import.meta.env as unknown as TerrainEnv
}

/** Post-fire terrain is active only when explicitly enabled AND a tiles URL is set. */
export function isPostfireTerrainEnabled(env: TerrainEnv = currentEnv()): boolean {
  return env.VITE_POSTFIRE_TERRAIN === 'true' && Boolean(env.VITE_POSTFIRE_TERRAIN_URL)
}

export function postfireTerrainConfig(env: TerrainEnv = currentEnv()): TerrainConfig {
  const maxzoom = Number(env.VITE_POSTFIRE_TERRAIN_MAXZOOM)
  return {
    tiles: String(env.VITE_POSTFIRE_TERRAIN_URL),
    encoding: (env.VITE_POSTFIRE_TERRAIN_ENCODING as DemEncoding) || 'terrarium',
    tileSize: 256,
    minzoom: 12,
    maxzoom: Number.isFinite(maxzoom) && maxzoom > 0 ? maxzoom : 17,
    bounds: POSTFIRE_DTM_BOUNDS,
    attribution:
      'Terrain: USGS 3DEP post-fire LiDAR DTM (OpenTopography OTSDEM.012025.6340.2, CC0)',
    vdatum: 'NAVD88/GEOID18 → WGS84 ellipsoidal (grid)',
  }
}

/** The terrain config the map should use right now (post-fire if enabled, else AWS). */
export function resolveTerrainConfig(env: TerrainEnv = currentEnv()): TerrainConfig {
  return isPostfireTerrainEnabled(env) ? postfireTerrainConfig(env) : AWS_TERRARIUM
}

/** Build a MapLibre raster-dem source spec from a terrain config. */
export function toDemSource(cfg: TerrainConfig): {
  type: 'raster-dem'
  encoding: DemEncoding
  tiles: string[]
  tileSize: number
  minzoom: number
  maxzoom: number
  bounds?: [number, number, number, number]
  attribution: string
} {
  return {
    type: 'raster-dem',
    encoding: cfg.encoding,
    tiles: [cfg.tiles],
    tileSize: cfg.tileSize,
    minzoom: cfg.minzoom,
    maxzoom: cfg.maxzoom,
    ...(cfg.bounds ? { bounds: cfg.bounds } : {}),
    attribution: cfg.attribution,
  }
}
