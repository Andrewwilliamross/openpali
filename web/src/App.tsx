import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { Map as MLMap } from 'maplibre-gl'
import MapView, { type GroundMode, type ViewMode } from './components/MapView'
import Header from './components/Header'
import ParcelDetailCard from './components/spatial/ParcelDetailCard'
import SearchBar from './components/SearchBar'
import Legend from './components/Legend'
import type { DetailsIndex, ParcelCollection, Summary } from './lib/types'
import { centroid } from './lib/format'
import { DATA_BASE } from './lib/config'

export default function App() {
  const [parcels, setParcels] = useState<ParcelCollection | null>(null)
  const [details, setDetails] = useState<DetailsIndex | null>(null)
  const [summary, setSummary] = useState<Summary | null>(null)
  const [selectedApn, setSelectedApn] = useState<string | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [mode, setMode] = useState<ViewMode>('3d')
  const [ground, setGround] = useState<GroundMode>('sat')
  const mapRef = useRef<MLMap | null>(null)

  useEffect(() => {
    Promise.all([
      fetch(`${DATA_BASE}/parcels.geojson`).then((r) => r.json()),
      fetch(`${DATA_BASE}/summary.json`).then((r) => r.json()),
    ])
      .then(([p, s]) => {
        setParcels(p)
        setSummary(s)
      })
      .catch(() => setLoadError('Could not load rebuild data. Try refreshing.'))
    // details are big-ish; load after first paint
    fetch(`${DATA_BASE}/details.json`)
      .then((r) => r.json())
      .then(setDetails)
      .catch(() => {})
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
          duration: 1400,
        })
    },
    [parcels, mode],
  )

  const handleGoto = useCallback((center: [number, number], zoom: number) => {
    mapRef.current?.flyTo({ center, zoom, duration: 1200 })
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
          onSelect={setSelectedApn}
          onMapReady={(m) => {
            mapRef.current = m
          }}
        />
        <SearchBar
          parcels={parcels}
          neighborhoods={summary?.neighborhoods ?? []}
          onPick={handlePickFromSearch}
          onGoto={handleGoto}
        />
        <button
          className="mode-toggle"
          onClick={() => setMode((m) => (m === '3d' ? '2d' : '3d'))}
          aria-label="Toggle 3D view"
        >
          {mode === '3d' ? '2D' : '3D'}
        </button>
        <button
          className="mode-toggle ground-toggle"
          onClick={() => setGround((g) => (g === 'sat' ? 'map' : 'sat'))}
          aria-label="Toggle ground imagery"
          title="Ground: current imagery (May 2026) vs map"
        >
          {ground === 'sat' ? 'Map' : 'Sat'}
        </button>
        <Legend />
        {loadError && <div className="load-error">{loadError}</div>}
        {selectedApn && (
          <ParcelDetailCard
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
