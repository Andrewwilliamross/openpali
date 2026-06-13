/**
 * Debug HUD scaffold (ROADMAP D10 — wiring only, no instrumentation yet).
 *
 * Enable with `?debug=1` or `localStorage.setItem('openpali:debug', '1')`.
 * Mounts an empty, unobtrusive panel; the 3D renderer will later populate
 * the `#debug-hud-stats` element with draw-list size, resident bytes, sort
 * time, and texture lifecycle counters.
 */

function debugHudEnabled(): boolean {
  try {
    if (new URLSearchParams(window.location.search).get('debug') === '1') return true
    return window.localStorage.getItem('openpali:debug') === '1'
  } catch {
    // no window / storage blocked — debug HUD simply stays off
    return false
  }
}

export default function DebugHud() {
  if (!debugHudEnabled()) return null
  return (
    <div className="debug-hud" aria-hidden="true">
      <div className="debug-hud-title">debug</div>
      <pre id="debug-hud-stats" className="debug-hud-stats">
        renderer stats pending
      </pre>
    </div>
  )
}
