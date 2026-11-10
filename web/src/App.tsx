import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { Map as MLMap } from 'maplibre-gl'
import MapView, { VIEW_PITCH } from './components/MapView'
import SearchBar from './components/SearchBar'
import { fetchMapData } from './lib/api'
import { motionMs } from './lib/format'
import { NEIGHBORHOODS, neighborhoodBounds } from './lib/neighborhoods'
import type { MapData } from './lib/types'

type Parcels =
  | { status: 'loading' }
  | { status: 'ready'; data: MapData }
  | { status: 'failed' }

export default function App() {
  const [parcels, setParcels] = useState<Parcels>({ status: 'loading' })
  const [selectedApn, setSelectedApn] = useState<string | null>(null)
  const mapRef = useRef<MLMap | null>(null)
  const data = parcels.status === 'ready' ? parcels.data : null

  useEffect(() => {
    const controller = new AbortController()
    fetchMapData(controller.signal)
      .then((d) => setParcels({ status: 'ready', data: d }))
      .catch(() => {
        if (!controller.signal.aborted) setParcels({ status: 'failed' })
      })
    return () => controller.abort()
  }, [])

  // a neighborhood's view is the extent of its scored (fire-destroyed) parcels
  const hoodBounds = useMemo(
    () => neighborhoodBounds((data?.parcels ?? []).filter((parcel) => parcel.score !== null)),
    [data],
  )

  const handlePick = useCallback(
    (apn: string) => {
      setSelectedApn(apn)
      // a parcel the release has no geometry for is still selectable, just not locatable
      const center = data?.parcels.find((parcel) => parcel.apn === apn)?.center
      if (!center) return
      mapRef.current?.flyTo({
        center,
        zoom: 17.6,
        pitch: VIEW_PITCH,
        duration: motionMs(1600),
        essential: true,
      })
    },
    [data],
  )

  const handleNeighborhood = useCallback(
    (name: string) => {
      const map = mapRef.current
      const hood = NEIGHBORHOODS.find((n) => n.name === name)
      if (!map || !hood) return
      const duration = motionMs(1600)
      const bounds = hoodBounds.get(name)
      if (bounds) {
        map.fitBounds(bounds, {
          pitch: VIEW_PITCH,
          bearing: map.getBearing(),
          padding: { top: 90, bottom: 40, left: 40, right: 40 },
          maxZoom: 16.6,
          duration,
          essential: true,
        })
      } else {
        map.flyTo({ center: hood.center, zoom: hood.zoom, pitch: VIEW_PITCH, duration, essential: true })
      }
    },
    [hoodBounds],
  )

  return (
    <div className="app">
      <MapView
        data={data}
        selectedApn={selectedApn}
        onSelect={setSelectedApn}
        onMapReady={(m) => {
          mapRef.current = m
        }}
      />
      <SearchBar parcels={data?.parcels ?? null} unavailable={parcels.status === 'failed'} onPick={handlePick} onNeighborhood={handleNeighborhood} />
      {parcels.status === 'failed' && (
        <p className="load-error" role="alert">
          Parcel data could not load. Start the evidence API with <code>make evidence-api</code>, then reload.
        </p>
      )}
    </div>
  )
}
