import type { Summary } from '../lib/types'
import { fmtNumber, fmtPct, fmtDate } from '../lib/format'

function Sparkline({ weekly }: { weekly: Summary['weekly'] }) {
  if (!weekly.length) return null
  const w = 120
  const h = 28
  const max = Math.max(...weekly.map((d) => d.issued), 1)
  const pts = weekly
    .map((d, i) => {
      const x = (i / Math.max(weekly.length - 1, 1)) * w
      const y = h - 2 - (d.issued / max) * (h - 6)
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
  const recent = weekly.slice(-4).reduce((s, d) => s + d.issued, 0)
  return (
    <div className="spark" title="Building permits issued per week">
      <svg width={w} height={h} aria-hidden>
        <polyline points={pts} fill="none" stroke="#1d4ed8" strokeWidth="1.6" />
      </svg>
      <div className="spark-label">
        <span className="metric-num">{recent}</span> permits / last 4 wks
      </div>
    </div>
  )
}

export default function Header({ summary }: { summary: Summary | null }) {
  const t = summary?.totals
  return (
    <header className="header">
      <div className="brand">
        <h1>Palisades Rebuild Tracker</h1>
        <span className="brand-sub">
          {summary ? `data as of ${fmtDate(summary.as_of.slice(0, 10))}` : 'loading…'}
        </span>
      </div>
      {t && (
        <div className="metrics">
          <div className="metric">
            <span className="metric-num">{fmtNumber(t.destroyed)}</span>
            <span className="metric-label">parcels destroyed</span>
          </div>
          <div className="metric">
            <span className="metric-num">{fmtPct(t.application_submitted, t.destroyed)}</span>
            <span className="metric-label">rebuild applications</span>
          </div>
          <div className="metric">
            <span className="metric-num">{fmtPct(t.permit_issued, t.destroyed)}</span>
            <span className="metric-label">permits issued</span>
          </div>
          <div className="metric" title="Certificates of Occupancy issued">
            <span className="metric-num">{fmtNumber(t.cofo_issued)}</span>
            <span className="metric-label">CofO issued</span>
          </div>
          <Sparkline weekly={summary.weekly} />
        </div>
      )}
    </header>
  )
}
