// The score→color ramp. Single source of truth for the MapLibre paint
// expression, the legend gradient, and badge colors.

export const SCORE_STOPS: [number, string][] = [
  [0, '#99000d'], // deep red — no activity
  [8, '#cb181d'], // lot cleared
  [15, '#f05e3d'], // application submitted
  [30, '#fd8d3c'], // plan check progressing
  [40, '#fdc23c'], // permitted
  [50, '#d0d943'], // construction starting
  [65, '#a4cf3f'], // framing
  [80, '#66bb52'], // finishing
  [92, '#3d9f47'], // finals
  [100, '#1b7837'], // complete
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

/** MapLibre data-driven fill color expression over the `score` property. */
export function scorePaintExpression(): unknown[] {
  const expr: unknown[] = ['interpolate', ['linear'], ['get', 'score']]
  for (const [stop, color] of SCORE_STOPS) expr.push(stop, color)
  return expr
}

export const STAGE_INFO: Record<number, { label: string; color: string }> = {
  0: { label: 'No activity', color: '#99000d' },
  1: { label: 'Lot cleared', color: '#cb181d' },
  2: { label: 'Plan check', color: '#fd8d3c' },
  3: { label: 'Permitted', color: '#fdc23c' },
  4: { label: 'Under construction', color: '#66bb52' },
  5: { label: 'Complete', color: '#1b7837' },
}

export const legendGradientCSS = `linear-gradient(to right, ${SCORE_STOPS.map(
  ([s, c]) => `${c} ${s}%`,
).join(', ')})`
