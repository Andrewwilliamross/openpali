// Floating property-evidence card. Shows parallel milestone lanes, the typed
// observation timeline (with per-observation status and source), pre-fire
// metadata, and public-record validation links.
//
// Deliberately absent (TRUTH-001): the retired 0-100 score, heuristic ETA,
// and forced stage ladder. "No public evidence" is always worded as absence
// from covered public sources — never as resident inactivity.

import { useEffect, useState } from 'react'
import type {
  LaneName,
  Observation,
  ParcelDetail,
  ParcelProps,
} from '../../lib/types'
import { LANE_SIGNAL_INFO, evidenceCategory } from '../../lib/colors'
import {
  fetchCoverage,
  GEOMETRY_SOURCE_LABELS,
  type CoverageEntry,
} from '../../lib/coverage'
import { fmtDate, fmtMoney, fmtNumber, titleCase } from '../../lib/format'
import { preFireTileUrl, WAYBACK_ATTRIBUTION } from '../../lib/imagery'
import CorrectionForm from './CorrectionForm'
import {
  fetchPostfirePicking,
  fetchPostfireSources,
  postfireSourceLabel,
  type PostfireSources,
} from '../../lib/postfire'

interface Props {
  apn: string
  props: ParcelProps | null
  detail: ParcelDetail | null
  onClose: () => void
}

const LANE_LABELS: Record<LaneName, string> = {
  cleanup: 'Cleanup',
  design_review: 'Design review',
  permitting: 'Permitting',
  construction: 'Construction',
  occupancy: 'Occupancy',
}

const EVENT_GLYPHS: Record<string, string> = {
  structure_destroyed: '◆',
  debris_removal_complete: '▣',
  cleanup_opt_out_selected: '⇄',
  cleanup_program_ineligible: '⊘',
  rebuild_application_submitted: '✎',
  plan_check_approved: '✔',
  rebuild_permit_issued: '✓',
  certificate_of_occupancy_issued: '⌂',
  construction_inspection_activity: '⚙',
  construction_inspection_passed: '⚙',
  ancillary_permit_activity: '·',
  non_rebuild_permit_activity: '·',
  inspection_activity: '·',
}

const STATUS_LABELS: Record<string, string> = {
  scheduled: 'scheduled',
  attempted: 'attempted',
  failed: 'failed',
  passed: 'passed',
  canceled: 'canceled',
  issued: 'issued',
  accepted: 'accepted',
  observed: 'observed',
  agency_reported: 'agency-reported',
  inferred: 'inferred',
  retracted: 'retracted',
  conflicting: 'conflicting sources',
  unavailable: 'unavailable',
  unknown: 'unknown',
}

function occurrenceText(o: Observation): string {
  if (o.occurred.kind === 'exact' && o.occurred.date) return fmtDate(o.occurred.date)
  if (o.occurred.kind === 'interval') {
    const from = o.occurred.earliest ? fmtDate(o.occurred.earliest) : null
    const to = o.occurred.latest ? fmtDate(o.occurred.latest) : null
    if (from && to) return `between ${from} and ${to}`
    if (from) return `on or after ${from}`
    if (to) return `by ${to}`
  }
  if (o.event_type.includes('inspection') && o.detail?.scheduled_for) {
    return `for ${fmtDate(o.detail.scheduled_for)}`
  }
  return 'date unknown'
}

export default function ParcelDetailCard({ apn, props, detail, onClose }: Props) {
  // The parent keys this component by APN, so selecting a different parcel
  // remounts it: entry animation is pure CSS and per-parcel state resets
  // without effect-driven setState churn.
  const [imgFailed, setImgFailed] = useState(false)
  const [coverage, setCoverage] = useState<CoverageEntry | null | undefined>(undefined)
  const [postfire, setPostfire] = useState<{
    sources: PostfireSources
    samples: number
  } | null>(null)

  // geometry-source badge (coverage.json): every 3D parcel carries its
  // provenance label — placeholders must never read as observations
  useEffect(() => {
    let alive = true
    void fetchCoverage().then((c) => {
      if (alive) setCoverage(c[apn] ?? null)
    })
    // post-fire surface coverage for THIS parcel (release-qualified asset)
    void Promise.all([fetchPostfireSources(), fetchPostfirePicking()]).then(
      ([sources, picking]) => {
        if (!alive || !sources?.surfel || !picking) return
        const entry = picking[apn]
        if (entry) setPostfire({ sources, samples: entry.n })
      },
    )
    return () => {
      alive = false
    }
  }, [apn])

  const category = props ? evidenceCategory(props) : null
  const apnFmt = `${apn.slice(0, 4)}-${apn.slice(4, 7)}-${apn.slice(7)}`
  const observations = detail ? [...detail.observations].reverse() : []
  const primaryPermit =
    detail?.permits.find((p) => p.qualification === 'qualifying_rebuild_application' && p.url) ??
    detail?.permits.find((p) => p.url) ??
    detail?.permits[0]
  const tileUrl = detail?.lat && detail?.lon ? preFireTileUrl(detail.lon, detail.lat) : null

  return (
    <aside className="spatial-card" aria-label="Property recovery evidence">
      <button className="spatial-card-close" onClick={onClose} aria-label="Close">×</button>

      {tileUrl && !imgFailed ? (
        <figure className="spatial-card-media">
          <img src={tileUrl} alt="Pre-fire aerial (historical context, not current conditions)"
               loading="lazy" onError={() => setImgFailed(true)} />
          <figcaption>Pre-fire · {WAYBACK_ATTRIBUTION}</figcaption>
        </figure>
      ) : null}

      {/* ---- identity header ---- */}
      <header className="spatial-card-head">
        <div className="spatial-head-text">
          <h2>{titleCase(detail?.address ?? props?.address ?? 'Unknown address')}</h2>
          <div className="spatial-sub">
            APN {apnFmt}
            {props?.neighborhood ? ` · ${props.neighborhood}` : ''}
            {props?.jurisdiction ? ` · ${props.jurisdiction === 'LA' ? 'City of LA' : props.jurisdiction === 'MALIBU' ? 'Malibu' : 'LA County'}` : ''}
          </div>
          {category && (
            <span className="spatial-stage" style={{ background: category.color }}>
              {category.label}
            </span>
          )}
          {coverage !== undefined && (
            <span
              className={`spatial-geom-badge${coverage?.geometry_source ? '' : ' spatial-geom-badge-none'}`}
              title={
                coverage?.geometry_source
                  ? `3D geometry: ${GEOMETRY_SOURCE_LABELS[coverage.geometry_source]}${coverage.acquired ? ` · source data ${coverage.acquired}` : ''}`
                  : 'This lot has no 3D geometry yet — it still counts in every statistic.'
              }
            >
              {coverage?.geometry_source
                ? GEOMETRY_SOURCE_LABELS[coverage.geometry_source]
                : 'No 3D geometry yet'}
            </span>
          )}
          {postfire && postfire.sources.surfel && (
            <span
              className="spatial-geom-badge"
              title={
                `${postfireSourceLabel(postfire.sources.surfel)} · ` +
                `${fmtNumber(postfire.samples)} ground samples on this parcel · ` +
                'a post-fire terrain observation, never evidence of current construction'
              }
            >
              Post-fire surface ({postfire.sources.surfel.acquisition_start?.slice(0, 10)})
            </span>
          )}
        </div>
      </header>

      {/* ---- parallel milestone lanes ---- */}
      {detail?.lanes && (
        <section>
          <h3 className="spatial-h">Recovery lanes</h3>
          <ul className="lane-strip">
            {detail.lanes.lanes.map((lane) => {
              const info = LANE_SIGNAL_INFO[lane.signal]
              return (
                <li key={lane.lane}>
                  <span className="lane-name">{LANE_LABELS[lane.lane]}</span>
                  <span className="lane-signal">
                    <span className="lane-dot" style={{ background: info.color }} aria-hidden />
                    {info.label}
                  </span>
                </li>
              )
            })}
          </ul>
          <p className="spatial-unknown-note">
            “No public evidence” means no event appears in the public sources
            OpenPali covers — it does not mean nothing is happening.
          </p>
        </section>
      )}

      {/* ---- typed evidence timeline ---- */}
      {observations.length > 0 && (
        <section>
          <h3 className="spatial-h">Public evidence</h3>
          <ol className="spatial-timeline">
            {observations.map((o) => (
              <li key={o.observation_id}>
                <span className="tl-glyph" aria-hidden>
                  {EVENT_GLYPHS[o.event_type] ?? '•'}
                </span>
                <div className="tl-body">
                  <span className="tl-name">
                    {o.label || o.event_type}
                    <span className="tl-status">{STATUS_LABELS[o.status] ?? o.status}</span>
                  </span>
                  <span className="tl-when">{occurrenceText(o)}</span>
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
                  {p.type}
                  {p.qualification === 'qualifying_rebuild_application'
                    ? ' · qualifying rebuild'
                    : p.qualification === 'rebuild_related_ancillary'
                      ? ' · rebuild-related'
                      : ''}
                  {p.submitted ? ` · filed ${fmtDate(p.submitted)}` : ''}
                  {p.issued ? ` · issued ${fmtDate(p.issued)}` : ''}
                  {p.valuation ? ` · ${fmtMoney(p.valuation)}` : ''}
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {primaryPermit?.url && (
        <a className="spatial-cta" href={primaryPermit.url} target="_blank" rel="noreferrer"
           title="Opens this permit in the City of LA open-data portal">
          Verify on LA City open data ↗
        </a>
      )}

      <CorrectionForm apn={apn} />
    </aside>
  )
}
