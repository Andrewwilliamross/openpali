import { EVIDENCE_CATEGORIES } from '../lib/colors'

export default function Legend() {
  return (
    <div className="legend" aria-label="Map legend: most advanced evidenced milestone">
      <div className="legend-title">Evidenced milestone</div>
      <ul className="legend-cats">
        {EVIDENCE_CATEGORIES.map((c) => (
          <li key={c.key}>
            <span className="legend-swatch" style={{ background: c.color }} aria-hidden />
            <span>{c.label}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
