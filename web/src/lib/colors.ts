// The score → colour ramp. Single source of truth for the draped parcel fills
// and the 3D structures.
//
// A parcel's rebuild score is computed by the release build
// (openpali.domain.lifecycles.REBUILD_SCORE): the position of its highest
// agency-reported recovery milestone on a 0–100 scale. Only parcels the agency
// fire assessment records as destroyed are scored.

export const SCORE_STOPS: [number, string][] = [
  [0, '#99000d'], // deep red — no milestone established
  [8, '#cb181d'], // lot cleared
  [15, '#f05e3d'], // application submitted
  [30, '#fd8d3c'], // plans approved
  [40, '#fdc23c'], // permitted
  [50, '#d0d943'], // construction starting
  [65, '#a4cf3f'], // construction under way
  [80, '#66bb52'], // finishing
  [92, '#3d9f47'], // construction complete
  [100, '#1b7837'], // occupancy
]

export function scoreColor(score: number): string {
  const s = Math.max(0, Math.min(100, score))
  for (let i = SCORE_STOPS.length - 1; i >= 0; i--) {
    const [stop, color] = SCORE_STOPS[i]
    if (s >= stop) {
      if (i === SCORE_STOPS.length - 1) return color
      const [next, nextColor] = SCORE_STOPS[i + 1]
      return lerpHex(color, nextColor, (s - stop) / (next - stop))
    }
  }
  return SCORE_STOPS[0][1]
}

function lerpHex(a: string, b: string, t: number): string {
  const pa = [1, 3, 5].map((i) => parseInt(a.slice(i, i + 2), 16))
  const pb = [1, 3, 5].map((i) => parseInt(b.slice(i, i + 2), 16))
  const out = pa.map((v, i) => Math.round(v + (pb[i] - v) * t))
  return '#' + out.map((v) => v.toString(16).padStart(2, '0')).join('')
}

/** MapLibre data-driven colour expression over a numeric score property. */
export function scorePaintExpression(property: string): unknown[] {
  const expr: unknown[] = ['interpolate', ['linear'], ['get', property]]
  for (const [stop, color] of SCORE_STOPS) expr.push(stop, color)
  return expr
}

export function scoreRgb(score: number): [number, number, number] {
  const hex = scoreColor(score)
  return [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16)) as [number, number, number]
}
