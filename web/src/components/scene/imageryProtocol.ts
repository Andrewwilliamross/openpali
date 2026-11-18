// `openpali-aerial://{z}/{x}/{y}`: one ground-imagery source for the map.
//
// `make imagery-mirror` keeps a WebP copy of the vendor's tiles around the
// release's parcels, in the vendor's own z/x/y scheme. A mirrored tile is a
// seventh of the bytes and comes from this host; everything else (the finest
// zoom, and anywhere away from the parcels) is fetched from the vendor as
// before, so the imagery has no edge and works with no mirror at all.
import maplibregl from 'maplibre-gl'

export const AERIAL_PROTOCOL = 'openpali-aerial'
export const AERIAL_TILES = `${AERIAL_PROTOCOL}://{z}/{x}/{y}`

interface Index {
  tiles: string
  maxzoom: number
  cover_zoom: number
  cover: [number, number][]
}

/** Which tiles the mirror holds: the cover tiles, everything finer inside
 *  them down to `maxzoom`, and every coarser tile above them. */
export function mirrored(index: Index): (z: number, x: number, y: number) => boolean {
  const held = new Set<string>()
  for (const [x, y] of index.cover) {
    for (let z = index.cover_zoom, s = 0; z >= 0; z--, s++) held.add(`${z}/${x >> s}/${y >> s}`)
  }
  return (z, x, y) => {
    if (z > index.maxzoom) return false
    const s = Math.max(0, z - index.cover_zoom)
    return held.has(`${z - s}/${x >> s}/${y >> s}`)
  }
}

let installedFor: string | null = null

export function installImageryProtocol(mirrorRoot: string, vendor: string): void {
  if (installedFor === mirrorRoot) return
  installedFor = mirrorRoot
  const resolver = fetch(`${mirrorRoot}/index.json`, { cache: 'no-cache' })
    .then(async (response) => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const index = (await response.json()) as Index
      return { has: mirrored(index), template: `${mirrorRoot}/${index.tiles}` }
    })
    // no mirror: every tile comes from the vendor
    .catch(() => ({ has: () => false, template: '' }))

  maplibregl.addProtocol(AERIAL_PROTOCOL, async (params, abort) => {
    const [z, x, y] = params.url.slice(`${AERIAL_PROTOCOL}://`.length).split('/')
    const { has, template } = await resolver
    const fill = (pattern: string): string =>
      pattern.replace('{z}', z).replace('{x}', x).replace('{y}', y)
    if (has(Number(z), Number(x), Number(y))) {
      const own = await fetch(fill(template), { signal: abort.signal })
      if (own.ok) return { data: await own.arrayBuffer() }
    }
    const response = await fetch(fill(vendor), { signal: abort.signal })
    if (!response.ok) throw new Error(`imagery tile ${z}/${x}/${y}: HTTP ${response.status}`)
    return { data: await response.arrayBuffer() }
  })
}
