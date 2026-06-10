// Pre-fire lot imagery from Esri World Imagery Wayback.
// Release 16453 is the last capture before the Jan 2025 fire (2024-08-15 imagery).
// Wayback uses {z}/{y}/{x} order (Y before X) — note the difference from standard XYZ.
// License: free to display with attribution (set on the card).

const WAYBACK_PREFIRE_RELEASE = 16453

export const WAYBACK_ATTRIBUTION =
  'Esri, Vantor, Earthstar Geographics, and the GIS User Community'

function lonLatToTile(lon: number, lat: number, z: number): { x: number; y: number } {
  const n = 2 ** z
  const x = Math.floor(((lon + 180) / 360) * n)
  const latRad = (lat * Math.PI) / 180
  const y = Math.floor(
    ((1 - Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) / 2) * n,
  )
  return { x, y }
}

/** 256px pre-fire aerial tile covering a lot's centroid (z18 ≈ lot/block scale). */
export function preFireTileUrl(lon: number, lat: number, z = 18): string {
  const { x, y } = lonLatToTile(lon, lat, z)
  return `https://wayback.maptiles.arcgis.com/arcgis/rest/services/world_imagery/wmts/1.0.0/default028mm/mapserver/tile/${WAYBACK_PREFIRE_RELEASE}/${z}/${y}/${x}`
}
