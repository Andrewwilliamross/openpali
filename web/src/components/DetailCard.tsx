import { useState } from 'react'
import type { ParcelDetail, ParcelProps } from '../lib/types'
import { STAGE_INFO, scoreColor } from '../lib/colors'
import { fmtDate, fmtMoney, fmtNumber, titleCase, daysAgo } from '../lib/format'
import { preFireTileUrl, WAYBACK_ATTRIBUTION } from '../lib/imagery'

interface Props {
  apn: string
  props: ParcelProps | null
  detail: ParcelDetail | null
  onClose: () => void
}

const EVENT_ICONS: Record<string, string> = {
  destroyed: '🔥',
  debris_cleared: '🚜',
  permit_submitted: '📄',
  permit_issued: '✅',
  inspection: '🔍',
  cofo: '🏠',
}

export default function DetailCard({ apn, props, detail, onClose }: Props) {
  const [imgFailed, setImgFailed] = useState(false)
  const stage = props ? STAGE_INFO[props.stage] : null
  const apnFmt = `${apn.slice(0, 4)}-${apn.slice(4, 7)}-${apn.slice(7)}`
  const events = detail ? [...detail.events].reverse() : []
  const primaryPermit = detail?.permits.find((p) => p.url) ?? detail?.permits[0]

  const tileUrl =
    detail?.lat && detail?.lon ? preFireTileUrl(detail.lon, detail.lat) : null

  return (
    <aside className="detail-card" aria-label="Parcel detail">
      <button className="card-close" onClick={onClose} aria-label="Close">
        ×
      </button>

      {tileUrl && !imgFailed ? (
        <figure className="card-img-wrap">
          <img
            className="card-img"
            src={tileUrl}
            alt="Pre-fire aerial view of the lot"
            loading="lazy"
            onError={() => setImgFailed(true)}
          />
          <figcaption className="card-img-cap">Pre-fire · {WAYBACK_ATTRIBUTION}</figcaption>
        </figure>
      ) : (
        <div className="card-img card-img-empty">no pre-fire image</div>
      )}

      <div className="card-body">
        <div className="card-title-row">
          <h2>{titleCase(detail?.address ?? props?.address ?? 'Unknown address')}</h2>
          {stage && (
            <span className="stage-chip" style={{ background: stage.color }}>
              {stage.label}
            </span>
          )}
        </div>
        <div className="card-sub">
          APN {apnFmt}
          {props?.neighborhood ? ` · ${props.neighborhood}` : ''}
        </div>

        {props && (
          <div className="score-row">
            <div className="score-bar">
              <div
                className="score-bar-fill"
                style={{ width: `${props.score}%`, background: scoreColor(props.score) }}
              />
            </div>
            <span className="score-num">{Math.round(props.score)}</span>
          </div>
        )}
        {detail?.score_explain && <p className="score-explain">{detail.score_explain}</p>}

        {detail?.est_completion && (
          <div className="est-row">
            Estimated completion: <strong>{detail.est_completion}</strong>
          </div>
        )}

        {detail && (
          <div className="facts">
            {detail.pre_fire.use && <span>{detail.pre_fire.use}</span>}
            {detail.pre_fire.year_built && <span>built {detail.pre_fire.year_built}</span>}
            {detail.pre_fire.sqft && <span>{fmtNumber(detail.pre_fire.sqft)} sqft</span>}
            {detail.pre_fire.beds && (
              <span>
                {detail.pre_fire.beds} bd / {detail.pre_fire.baths ?? '?'} ba
              </span>
            )}
          </div>
        )}

        {events.length > 0 && (
          <>
            <h3 className="section-h">Timeline</h3>
            <ol className="timeline">
              {events.map((e, i) => (
                <li key={i} className={i === 0 ? 'tl-latest' : ''}>
                  <span className="tl-icon">{EVENT_ICONS[e.kind] ?? '•'}</span>
                  <span className="tl-label">{e.label}</span>
                  <span className="tl-date" title={daysAgo(e.date)}>
                    {fmtDate(e.date)}
                  </span>
                </li>
              ))}
            </ol>
          </>
        )}

        {detail && detail.permits.length > 0 && (
          <>
            <h3 className="section-h">Permits</h3>
            <ul className="permits">
              {detail.permits.map((p) => (
                <li key={p.no}>
                  <div className="permit-row">
                    <span className="permit-no">
                      {p.url ? (
                        <a href={p.url} target="_blank" rel="noreferrer">
                          {p.no}
                        </a>
                      ) : (
                        p.no
                      )}
                    </span>
                    <span className="permit-status">{p.status}</span>
                  </div>
                  <div className="permit-meta">
                    {p.type} · filed {fmtDate(p.submitted)}
                    {p.issued ? ` · issued ${fmtDate(p.issued)}` : ''}
                    {p.valuation ? ` · ${fmtMoney(p.valuation)}` : ''}
                  </div>
                </li>
              ))}
            </ul>
          </>
        )}

        {primaryPermit?.url && (
          <a className="ladbs-link" href={primaryPermit.url} target="_blank" rel="noreferrer">
            View official permit record ↗
          </a>
        )}
      </div>
    </aside>
  )
}
