// Serving endpoints (ADR 0001, Decision 5 — decouple serving from the repo).
//
// Defaults reproduce the current behavior exactly: data + tiles are read from the
// bundled static paths under BASE_URL. Point these at object storage / a CDN in
// production by setting VITE_DATA_BASE / VITE_TILES_BASE at build time (e.g. in
// web/.env.production). No trailing slash.
const BASE = import.meta.env.BASE_URL

const env = import.meta.env as unknown as Record<string, string | undefined>

export const DATA_BASE = env.VITE_DATA_BASE ?? `${BASE}data`
export const TILES_BASE = env.VITE_TILES_BASE ?? `${BASE}tiles/palisades`
