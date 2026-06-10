import { useEffect, useRef } from 'react'
import maplibregl, { Map as MLMap, MapMouseEvent } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import type { ParcelCollection } from '../lib/types'
import { scorePaintExpression } from '../lib/colors'

const BASEMAP = 'https://tiles.openfreemap.org/styles/positron'
const PALISADES_CENTER: [number, number] = [-118.5295, 34.0465]

interface Props {
  parcels: ParcelCollection | null
  selectedApn: string | null
  onSelect: (apn: string | null) => void
  onMapReady: (map: MLMap) => void
}

export default function MapView({ parcels, selectedApn, onSelect, onMapReady }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MLMap | null>(null)
  const hoveredRef = useRef<string | number | null>(null)
  const loadedRef = useRef(false)

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: BASEMAP,
      center: PALISADES_CENTER,
      zoom: 13.2,
      minZoom: 10,
      maxZoom: 19,
      attributionControl: { compact: true },
    })
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right')
    mapRef.current = map
    // expose for E2E checks and debugging
    ;(window as unknown as { __map?: MLMap }).__map = map
    map.on('load', () => {
      loadedRef.current = true
      onMapReady(map)
    })
    // The map can mount before its flex container has resolved its final height;
    // keep the GL canvas in sync with the container size.
    const ro = new ResizeObserver(() => map.resize())
    ro.observe(containerRef.current)
    return () => {
      ro.disconnect()
      map.remove()
      mapRef.current = null
      loadedRef.current = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Add/refresh the parcel source + layers once both map and data are ready.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !parcels) return

    const install = () => {
      // Clear any stale hover state when (re)installing data.
      hoveredRef.current = null
      if (map.getSource('parcels')) {
        ;(map.getSource('parcels') as maplibregl.GeoJSONSource).setData(parcels)
        return
      }
      map.addSource('parcels', { type: 'geojson', data: parcels, promoteId: 'apn' })
      map.addLayer({
        id: 'parcel-fill',
        type: 'fill',
        source: 'parcels',
        paint: {
          'fill-color': scorePaintExpression() as never,
          'fill-opacity': [
            'case',
            ['boolean', ['feature-state', 'hover'], false],
            0.95,
            0.78,
          ] as never,
        },
      })
      map.addLayer({
        id: 'parcel-line',
        type: 'line',
        source: 'parcels',
        paint: {
          'line-color': '#ffffff',
          'line-width': ['interpolate', ['linear'], ['zoom'], 13, 0.2, 16, 0.8] as never,
          'line-opacity': 0.55,
        },
      })
      map.addLayer({
        id: 'parcel-selected',
        type: 'line',
        source: 'parcels',
        filter: ['==', ['get', 'apn'], ''],
        paint: { 'line-color': '#1d4ed8', 'line-width': 3 },
      })

      map.on('mousemove', 'parcel-fill', (e: MapMouseEvent) => {
        map.getCanvas().style.cursor = 'pointer'
        const f = (e as MapMouseEvent & { features?: maplibregl.MapGeoJSONFeature[] })
          .features?.[0]
        if (!f || f.id === hoveredRef.current) return
        if (hoveredRef.current != null)
          map.setFeatureState({ source: 'parcels', id: hoveredRef.current }, { hover: false })
        hoveredRef.current = f.id ?? null
        if (f.id != null)
          map.setFeatureState({ source: 'parcels', id: f.id }, { hover: true })
      })
      map.on('mouseleave', 'parcel-fill', () => {
        map.getCanvas().style.cursor = ''
        if (hoveredRef.current != null)
          map.setFeatureState({ source: 'parcels', id: hoveredRef.current }, { hover: false })
        hoveredRef.current = null
      })
      map.on('click', 'parcel-fill', (e: MapMouseEvent) => {
        const f = (e as MapMouseEvent & { features?: maplibregl.MapGeoJSONFeature[] })
          .features?.[0]
        onSelect(f ? String(f.properties.apn) : null)
      })
      map.on('click', (e) => {
        const hits = map.queryRenderedFeatures(e.point, { layers: ['parcel-fill'] })
        if (!hits.length) onSelect(null)
      })
    }

    if (loadedRef.current) install()
    else map.once('load', install)
  }, [parcels, onSelect])

  // Selection highlight.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !loadedRef.current || !map.getLayer('parcel-selected')) return
    map.setFilter('parcel-selected', ['==', ['get', 'apn'], selectedApn ?? ''])
  }, [selectedApn])

  return <div ref={containerRef} className="map-container" />
}
