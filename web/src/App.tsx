import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import type { Map as MLMap } from 'maplibre-gl'
import MapView, { type GroundMode, type SpatialStatus, type ViewMode } from './components/MapView'
import Header from './components/Header'
import ParcelDetailCard from './components/spatial/ParcelDetailCard'
import SearchBar from './components/SearchBar'
import Legend from './components/Legend'
import DebugHud from './components/DebugHud'
import type { DetailsIndex, ParcelCollection, Summary } from './lib/types'
import { centroid, motionMs } from './lib/format'
import { fetchPostfireSources } from './lib/postfire'

const BASE = import.meta.env.BASE_URL

export default function App() {
  const [parcels, setParcels] = useState<ParcelCollection | null>(null)
  const [details, setDetails] = useState<DetailsIndex | null>(null)
  // one snapshot everywhere (PUB-001): the static bundle is the base (and the
  // last-known-good when the API is down); release-manifest numbers overlay it
  const [staticSummary, setStaticSummary] = useState<Summary | null>(null)
  const [releaseSummary, setReleaseSummary] = useState<{
    as_of: string
    snapshot_id: string
    totals: Partial<Summary['totals']>
  } | null>(null)
  const summary = useMemo<Summary | null>(() => {
    if (!staticSummary) return null
    if (!releaseSummary) return staticSummary
    return {
      ...staticSummary,
      as_of: releaseSummary.as_of || staticSummary.as_of,
      snapshot_id: releaseSummary.snapshot_id,
      totals: { ...staticSummary.totals, ...releaseSummary.totals },
    }
  }, [staticSummary, releaseSummary])
  // property selection lives in the URL: /property/:apn is a shareable,
  // reload-safe journey; closing the card returns to /map
  const { apn: routeApn } = useParams<{ apn: string }>()
  const navigate = useNavigate()
  const selectedApn = routeApn && /^\d{10}$/.test(routeApn) ? routeApn : null
  const setSelectedApn = useCallback(
    (next: string | null) => {
      navigate(next ? `/property/${next}` : '/map')
    },
    [navigate],
  )
  const [loadError, setLoadError] = useState<string | null>(null)
  // 2D-first: 3D loads ONLY on request (SPATIAL-002), and the vendor ground
  // imagery is opt-in (GOV-001 safe default — EagleView WMTS rights are
  // county-account terms, not ours to presume)
  const [mode, setMode] = useState<ViewMode>('2d')
  const [ground, setGround] = useState<GroundMode>('map')
  // LARIAC-derived pre-fire 3D corpus: rights unresolved -> explicit opt-in
  const [prefire, setPrefire] = useState(false)
  // capability probe: never offer 3D where WebGL2 does not exist
  const webglOk = useMemo(() => {
    try {
      return document.createElement('canvas').getContext('webgl2') !== null
    } catch {
      return false
    }
  }, [])
  // lifecycle of the code-split 3D renderer chunk (MapView reports it)
  const [spatialStatus, setSpatialStatus] = useState<SpatialStatus>('idle')
  const mapRef = useRef<MLMap | null>(null)

  const handleSpatialStatus = useCallback((status: SpatialStatus) => {
    setSpatialStatus(status)
    // chunk fetch failed (offline / flaky connection): revert the toggle so
    // the 2D tracker keeps working; the retry chip re-arms the fetch
    if (status === 'error') setMode('2d')
  }, [])

  // visible release identity: everything on screen belongs to ONE pinned
  // release/snapshot; when the API is unreachable the static bundle serves
  // as clearly-labeled last-known-good
  const [releaseInfo, setReleaseInfo] = useState<{
    releaseId: string
    snapshotId: string
    publishedAt: string | null
  } | null>(null)

  useEffect(() => {
    Promise.all([
      fetch(`${BASE}data/parcels.geojson`).then((r) => r.json()),
      fetch(`${BASE}data/summary.json`).then((r) => r.json()),
    ])
      .then(([p, s]) => {
        setParcels(p)
        setStaticSummary(s)
      })
      .catch(() => setLoadError('Could not load rebuild data. Try refreshing.'))
    // details are big-ish; load after first paint
    fetch(`${BASE}data/details.json`)
      .then((r) => r.json())
      .then(setDetails)
      .catch(() => {})
    // release-pinned header numbers (PUB-001/FRONTEND-002): coverage counts
    // straight from the current release manifest
    void (async () => {
      const pf = await fetchPostfireSources()
      if (!pf) return
      try {
        const { releaseInfoV1ReleasesReleaseIdGet } = await import('./api/generated/sdk.gen')
        const resp = await releaseInfoV1ReleasesReleaseIdGet({
          path: { release_id: pf.releaseId },
        })
        if (!resp.data) return
        const rel = resp.data as {
          release_id: string
          snapshot_id: string
          published_at?: string | null
          coverage?: Record<string, number | null>
        }
        setReleaseInfo({
          releaseId: rel.release_id,
          snapshotId: rel.snapshot_id,
          publishedAt: rel.published_at ?? null,
        })
        const c = rel.coverage ?? {}
        const totals: Partial<Summary['totals']> = {}
        if (c.properties != null) totals.destroyed = c.properties
        if (c.cleanup_complete != null) totals.cleanup_complete = c.cleanup_complete
        if (c.application_submitted != null) totals.application_submitted = c.application_submitted
        if (c.plan_check_approved != null) totals.plan_check_approved = c.plan_check_approved
        if (c.permit_issued != null) totals.permit_issued = c.permit_issued
        if (c.construction_evidence != null) totals.construction_evidence = c.construction_evidence
        if (c.cofo_issued != null) totals.cofo_issued = c.cofo_issued
        setReleaseSummary({
          as_of: rel.published_at ?? '',
          snapshot_id: rel.snapshot_id,
          totals,
        })
      } catch {
        /* static summary remains the LKG */
      }
    })()
  }, [])

  const selectedProps = useMemo(() => {
    if (!selectedApn || !parcels) return null
    return parcels.features.find((f) => f.properties.apn === selectedApn)?.properties ?? null
  }, [selectedApn, parcels])

  const handlePickFromSearch = useCallback(
    (apn: string) => {
      setSelectedApn(apn)
      const f = parcels?.features.find((x) => x.properties.apn === apn)
      if (f && mapRef.current)
        mapRef.current.flyTo({
          center: centroid(f.geometry),
          zoom: 17.4,
          pitch: mode === '3d' ? 58 : 0,
          duration: motionMs(1400),
        })
    },
    [parcels, mode, setSelectedApn],
  )

  const handleGoto = useCallback((center: [number, number], zoom: number) => {
    mapRef.current?.flyTo({ center, zoom, duration: motionMs(1200) })
  }, [])

  return (
    <div className="app">
      <Header summary={summary} />
      <div className="map-wrap">
        <MapView
          parcels={parcels}
          selectedApn={selectedApn}
          mode={mode}
          ground={ground}
          prefire={prefire}
          onSelect={setSelectedApn}
          onMapReady={(m) => {
            mapRef.current = m
          }}
          onSpatialStatus={handleSpatialStatus}
        />
        <SearchBar
          parcels={parcels}
          neighborhoods={summary?.neighborhoods ?? []}
          onPick={handlePickFromSearch}
          onGoto={handleGoto}
        />
        <button
          className={`mode-toggle${spatialStatus === 'loading' ? ' mode-toggle-loading' : ''}`}
          onClick={() => setMode((m) => (m === '3d' ? '2d' : '3d'))}
          aria-label="Toggle 3D view"
          aria-busy={spatialStatus === 'loading'}
          disabled={!webglOk}
          title={webglOk ? undefined : '3D is unavailable on this device (no WebGL2); the 2D tracker has every capability'}
        >
          {spatialStatus === 'loading' ? '3D…' : mode === '3d' ? '2D' : '3D'}
        </button>
        {mode === '3d' && (
          <button
            className="mode-toggle prefire-toggle"
            onClick={() => setPrefire((p) => !p)}
            aria-pressed={prefire}
            aria-label="Toggle pre-fire county model"
            title="LARIAC-derived pre-fire structures; county license terms pending — off by default"
          >
            {prefire ? 'Hide pre-fire model' : 'Pre-fire model (rights pending)'}
          </button>
        )}
        <button
          className="mode-toggle ground-toggle"
          onClick={() => setGround((g) => (g === 'sat' ? 'map' : 'sat'))}
          aria-label="Toggle ground imagery"
          title="Ground: current imagery (May 2026) vs map"
        >
          {ground === 'sat' ? 'Map' : 'Sat'}
        </button>
        <Legend mode={mode} />
        <nav className="app-nav" aria-label="Site">
          <a href="/methods">Methods</a>
          <a href="/status">Status</a>
        </nav>
        <div
          className="release-badge"
          data-testid="release-badge"
          title={
            releaseInfo
              ? `Every number, color, and timeline on this page comes from this one release`
              : 'The data API is unreachable; showing the bundled last-known-good data'
          }
        >
          {releaseInfo
            ? `release ${releaseInfo.releaseId.slice(0, 16)} · snapshot ${releaseInfo.snapshotId.slice(0, 17)}`
            : 'offline · last-known-good data'}
        </div>
        <DebugHud />
        {loadError && <div className="load-error">{loadError}</div>}
        {spatialStatus === 'error' && (
          <div className="spatial-load-error" role="alert">
            <span>3D view failed to load.</span>
            <button onClick={() => setMode('3d')}>Retry</button>
          </div>
        )}
        {selectedApn && (
          <ParcelDetailCard
            key={selectedApn}
            apn={selectedApn}
            props={selectedProps}
            detail={details?.[selectedApn] ?? null}
            onClose={() => setSelectedApn(null)}
          />
        )}
      </div>
    </div>
  )
}
