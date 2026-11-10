// `openpali-dem://{z}/{x}/{y}`: one elevation source for the map.
//
// The scene build bakes terrain tiles only where the USGS post-fire lidar
// improves on the regional terrain, and registers every structure against
// that same surface. Everywhere else the regional (Mapzen) tile is the right
// answer and is fetched directly, so nothing regional is re-hosted and the
// terrain has no edge.
import maplibregl from 'maplibre-gl'
import { loadScene } from './manifest'

export const TERRAIN_PROTOCOL = 'openpali-dem'
export const TERRAIN_TILES = `${TERRAIN_PROTOCOL}://{z}/{x}/{y}`
/** Used when the scene has no baked terrain (or cannot be loaded). */
const REGIONAL = 'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png'
const REGIONAL_MAXZOOM = 15
/** Marks the one expected failure: a zoom-16 tile the lidar does not cover.
 *  MapLibre then draws that area from its zoom-15 parent. */
export const NOT_BAKED = 'openpali-dem: no finer terrain here'

interface Resolver {
  baked: Set<string>
  template: string | null
  regional: string
  regionalMaxzoom: number
}

let installedFor: string | null = null

export function installTerrainProtocol(sceneRoot: string): void {
  if (installedFor === sceneRoot) return
  installedFor = sceneRoot
  const resolver: Promise<Resolver> = loadScene(sceneRoot)
    .then(({ base, manifest }) => {
      const terrain = manifest.terrain
      const baked = new Set<string>()
      for (const [z, tiles] of Object.entries(terrain?.index ?? {})) {
        for (const [x, y] of tiles) baked.add(`${z}/${x}/${y}`)
      }
      return {
        baked,
        template: terrain ? `${base}/${terrain.tiles}` : null,
        regional: terrain?.fallback ?? REGIONAL,
        regionalMaxzoom: terrain?.fallback_maxzoom ?? REGIONAL_MAXZOOM,
      }
    })
    // no scene: the map still gets regional terrain
    .catch(() => ({ baked: new Set<string>(), template: null, regional: REGIONAL, regionalMaxzoom: REGIONAL_MAXZOOM }))

  maplibregl.addProtocol(TERRAIN_PROTOCOL, async (params, abort) => {
    const [z, x, y] = params.url.slice(`${TERRAIN_PROTOCOL}://`.length).split('/')
    const { baked, template, regional, regionalMaxzoom } = await resolver
    const fill = (pattern: string): string =>
      pattern.replace('{z}', z).replace('{x}', x).replace('{y}', y)
    let url: string
    if (template && baked.has(`${z}/${x}/${y}`)) url = fill(template)
    else if (Number(z) <= regionalMaxzoom) url = fill(regional)
    else throw new Error(NOT_BAKED)
    const response = await fetch(url, { signal: abort.signal })
    if (!response.ok) throw new Error(`terrain tile ${z}/${x}/${y}: HTTP ${response.status}`)
    return { data: await response.arrayBuffer() }
  })
}
