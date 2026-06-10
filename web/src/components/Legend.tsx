import { legendGradientCSS } from '../lib/colors'

export default function Legend() {
  return (
    <div className="legend">
      <div className="legend-bar" style={{ background: legendGradientCSS }} />
      <div className="legend-labels">
        <span>No permit</span>
        <span>Plan check</span>
        <span>Permitted</span>
        <span>Building</span>
        <span>Done</span>
      </div>
    </div>
  )
}
