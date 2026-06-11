// Floating structural-intelligence card — replaces the docked sidebar.
// Context-aware overlay: slides in on selection, score header with a
// stage-matched glow, scannable construction-milestone timeline, grouped
// pre-fire metadata, and public-record validation links.

import { useEffect, useState } from 'react'
import type { ParcelDetail, ParcelProps } from '../../lib/types'
import { STAGE_INFO, scoreColor } from '../../lib/colors'
import { fmtDate, fmtMoney, fmtNumber, titleCase } from '../../lib/format'
import { preFireTileUrl, WAYBACK_ATTRIBUTION } from '../../lib/imagery'

interface Props {
  apn: string
  props: ParcelProps | null
  detail: ParcelDetail | null
  onClose: () => void
}

// LADBS inspection sequence rendered as explicit named milestones
const MILESTONE_LABELS: Record<string, string> = {
  destroyed: 'Structure Lost',
  debris_cleared: 'Site Cleared',
  permit_submitted: 'Plans Submitted',
  permit_issued: 'Building Permit Issued',
  inspection: 'Construction Inspection',
  cofo: 'Certificate of Occupancy',
}

const MILESTONE_GLYPHS: Record<string, string> = {
  destroyed: '◆',
  debris_cleared: '▣',
  permit_submitted: '✎',
  permit_issued: '✓',
  inspection: '⚙',
  cofo: '⌂',
}

export default function ParcelDetailCard({ apn, props, detail, onClose }: Props) {
  const [entered, setEntered] = useState(false)
  const [imgFailed, setImgFailed] = useState(false)

  useEffect(() => {
    setEntered(false)
    setImgFailed(false)
    const t = requestAnimationFrame(() => setEntered(true))
    return () => cancelAnimationFrame(t)
  }, [apn])

  const stage = props ? STAGE_INFO[props.stage] : null
  const score = props?.score ?? detail?.score ?? 0
  const glow = scoreColor(score)
  const apnFmt = `${apn.slice(0, 4)}-${apn.slice(4, 7)}-${apn.slice(7)}`
  const events = detail ? [...detail.events].reverse() : []
  const primaryPermit = detail?.permits.find((p) => p.url) ?? detail?.permits[0]
  const tileUrl = detail?.lat && detail?.lon ? preFireTileUrl(detail.lon, detail.lat) : null

  return (
    <aside className={`spatial-card ${entered ? 'spatial-card-in' : ''}`}
           aria-label="Structural intelligence">
      <button className="spatial-card-close" onClick={onClose} aria-label="Close">×</button>

      {tileUrl && !imgFailed ? (
        <figure className="spatial-card-media">
          <img src={tileUrl} alt="Pre-fire aerial" loading="lazy"
               onError={() => setImgFailed(true)} />
          <figcaption>Pre-fire · {WAYBACK_ATTRIBUTION}</figcaption>
        </figure>
      ) : null}

      {/* ---- rebuild metrics header ---- */}
      <header className="spatial-card-head">
        <div className="spatial-score" style={{ color: glow, textShadow: `0 0 18px ${glow}88, 0 0 4px ${glow}55` }}>
          {Math.round(score)}
        </div>
        <div className="spatial-head-text">
          <h2>{titleCase(detail?.address ?? props?.address ?? 'Unknown address')}</h2>
          <div className="spatial-sub">
            APN {apnFmt}
            {props?.neighborhood ? ` · ${props.neighborhood}` : ''}
          </div>
          {stage && (
            <span className="spatial-stage" style={{ background: stage.color }}>
              {stage.label}
            </span>
          )}
        </div>
      </header>

      {detail?.score_explain && <p className="spatial-explain">{detail.score_explain}</p>}
      {detail?.est_completion && (
        <div className="spatial-eta">
          Estimated completion <strong>{detail.est_completion}</strong>
        </div>
      )}

      {/* ---- administrative inspection timeline ---- */}
      {events.length > 0 && (
        <section>
          <h3 className="spatial-h">Inspection timeline</h3>
          <ol className="spatial-timeline">
            {events.map((e, i) => (
              <li key={i} className={i === 0 ? 'tl-now' : ''}>
                <span className="tl-glyph" aria-hidden>
                  {MILESTONE_GLYPHS[e.kind] ?? '•'}
                </span>
                <div className="tl-body">
                  <span className="tl-name">{e.label || MILESTONE_LABELS[e.kind]}</span>
                  <span className="tl-when">{fmtDate(e.date)}</span>
                </div>
              </li>
            ))}
          </ol>
        </section>
      )}

      {/* ---- metadata grouping ---- */}
      {detail && (
        <section>
          <h3 className="spatial-h">Pre-fire structure</h3>
          <dl className="spatial-meta">
            {detail.pre_fire.use && (<><dt>Use</dt><dd>{detail.pre_fire.use}</dd></>)}
            {detail.pre_fire.year_built && (<><dt>Built</dt><dd>{detail.pre_fire.year_built}</dd></>)}
            {detail.pre_fire.sqft && (<><dt>Area</dt><dd>{fmtNumber(detail.pre_fire.sqft)} sqft</dd></>)}
            {detail.pre_fire.beds != null && (<><dt>Bed / Bath</dt>
              <dd>{detail.pre_fire.beds} / {detail.pre_fire.baths ?? '–'}</dd></>)}
            {detail.pre_fire.units != null && detail.pre_fire.units > 1 && (
              <><dt>Units</dt><dd>{detail.pre_fire.units}</dd></>)}
          </dl>
        </section>
      )}

      {detail && detail.permits.length > 0 && (
        <section>
          <h3 className="spatial-h">Permits</h3>
          <ul className="spatial-permits">
            {detail.permits.map((p) => (
              <li key={p.no}>
                <div className="permit-line">
                  {p.url
                    ? <a href={p.url} target="_blank" rel="noreferrer">{p.no}</a>
                    : <span>{p.no}</span>}
                  <em>{p.status}</em>
                </div>
                <div className="permit-line-sub">
                  {p.type} · filed {fmtDate(p.submitted)}
                  {p.issued ? ` · issued ${fmtDate(p.issued)}` : ''}
                  {p.valuation ? ` · ${fmtMoney(p.valuation)}` : ''}
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {primaryPermit?.url && (
        <a className="spatial-cta" href={primaryPermit.url} target="_blank" rel="noreferrer">
          Validate against official record ↗
        </a>
      )}
    </aside>
  )
}
