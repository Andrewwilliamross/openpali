import { useEffect, useRef } from 'react'
import maplibregl, { Map as MLMap, MapMouseEvent } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import type { ParcelCollection } from '../lib/types'
import { scorePaintExpression } from '../lib/colors'
import { SplatRenderLayer } from './spatial/SplatRenderLayer'
import { SpatialIntersector } from './spatial/spatial_intersector'

const BASEMAP = 'https://tiles.openfreemap.org/styles/positron'
const PALISADES_CENTER: [number, number] = [-118.5295, 34.0465]
const TILES_BASE = `${import.meta.env.BASE_URL}tiles/palisades`

// AWS Open Data terrain tiles (Mapzen terrarium). maxzoom 15 is mandatory —
// z16 does not exist upstream and must overzoom, not 404.
const DEM_TILES = 'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png'
const DEM_ATTRIBUTION = 'Terrain: USGS 3DEP/SRTM via Mapzen terrain tiles (AWS Open Data)'

// Ground imagery, two stacked sources:
// 1. PRIMARY — EagleView "CALOSA26" 2026 mosaic from the county's public
//    LARIAC WMTS account: the newest public capture of actual ground
//    conditions (cleared pads AND active rebuilds). Layer id re-derived from
//    the account's WMTS GetCapabilities (svc.pictometry.com/Image/<acct>/wmts)
//    — that document is the source of truth when the vendor rotates keys.
//    Full pyramid z11–21 (probe-verified). The service flaps occasionally
//    (observed 404-at-all-zooms outages); MapLibre then falls through to the
//    world layer below: degraded vintage, never a blank map.
// 2. FALLBACK — Esri World Imagery (Wayback) under it, so the world doesn't
//    go blank at the coverage edge or during vendor outages. NOTE: the world
//    mosaic over the Palisades still shows PRE-fire structures (Wayback
//    release dates are publish dates, not capture dates).
const GROUND26_TILES =
  'https://svc.pictometry.com/Image/BCC27E3E-766E-CE0B-7D11-AA4760AC43ED/wmts/PICT-CALOSA26-WX2j52mKfq/default/GoogleMapsCompatible/{z}/{x}/{y}.png'
// CALOSA26-145 WMTS advertised extent (EPSG:3857) → WGS84 bounds for the source
const GROUND26_BOUNDS: [number, number, number, number] =
  [-118.9998, 33.6569, -117.6031, 34.8690]
const GROUND26_ATTRIBUTION =
  'Imagery: EagleView 2026 Mosaic (LA County LARIAC WMTS)'
const WORLD_IMAGERY_TILES =
  'https://wayback.maptiles.arcgis.com/arcgis/rest/services/world_imagery/wmts/1.0.0/default028mm/mapserver/tile/10842/{z}/{y}/{x}'
const WORLD_IMAGERY_ATTRIBUTION =
  'Esri World Imagery — Esri, Vantor, Earthstar Geographics'

export type ViewMode = '2d' | '3d'
export type GroundMode = 'map' | 'sat'

interface Props {
  parcels: ParcelCollection | null
  selectedApn: string | null
  mode: ViewMode
  ground: GroundMode
  onSelect: (apn: string | null) => void
  onMapReady: (map: MLMap) => void
}

function demSource(): maplibregl.RasterDEMSourceSpecification {
  return {
    type: 'raster-dem',
    encoding: 'terrarium',
    tiles: [DEM_TILES],
    tileSize: 256,
    minzoom: 0,
    maxzoom: 15,
    attribution: DEM_ATTRIBUTION,
  }
}

export default function MapView({ parcels, selectedApn, mode, ground, onSelect, onMapReady }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MLMap | null>(null)
  const hoveredRef = useRef<string | number | null>(null)
  const loadedRef = useRef(false)
  const splatLayerRef = useRef<SplatRenderLayer | null>(null)
  const intersectorRef = useRef<SpatialIntersector | null>(null)
  const modeRef = useRef<ViewMode>(mode)
  modeRef.current = mode
  const groundRef = useRef<GroundMode>(ground)
  groundRef.current = ground

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: BASEMAP,
      center: PALISADES_CENTER,
      zoom: 13.6,
      pitch: 62,
      maxPitch: 85,
      minZoom: 10,
      maxZoom: 19,
      attributionControl: { compact: true },
    })
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'bottom-right')
    mapRef.current = map
    // expose for E2E checks and debugging
    ;(window as unknown as { __map?: MLMap }).__map = map

    map.on('load', () => {
      loadedRef.current = true

      // ---- terrain + hillshade (separate source instances, per ML guidance) ----
      map.addSource('terrain-dem', demSource())
      map.addSource('hillshade-dem', demSource())
      // current-conditions ground imagery (drapes natively on the terrain):
      // world fallback below, county post-fire flight on top within its bounds
      map.addSource('ground-imagery-world', {
        type: 'raster',
        tiles: [WORLD_IMAGERY_TILES],
        tileSize: 256,
        maxzoom: 19,
        attribution: WORLD_IMAGERY_ATTRIBUTION,
      })
      map.addSource('ground-imagery', {
        type: 'raster',
        tiles: [GROUND26_TILES],
        tileSize: 256,
        // the WMTS serves nothing below z11 (404s) — without minzoom MapLibre
        // requests far-field low-zoom tiles at oblique pitch and logs failures
        minzoom: 11,
        maxzoom: 21,
        bounds: GROUND26_BOUNDS,
        attribution: GROUND26_ATTRIBUTION,
      })
      map.addLayer(
        {
          id: 'ground-imagery-world',
          type: 'raster',
          source: 'ground-imagery-world',
          layout: { visibility: groundRef.current === 'sat' ? 'visible' : 'none' },
          paint: { 'raster-opacity': 1 },
        },
        firstSymbolLayerId(map),
      )
      map.addLayer(
        {
          id: 'ground-imagery',
          type: 'raster',
          source: 'ground-imagery',
          layout: { visibility: groundRef.current === 'sat' ? 'visible' : 'none' },
          paint: { 'raster-opacity': 1 },
        },
        firstSymbolLayerId(map),
      )
      map.addLayer(
        {
          id: 'hills',
          type: 'hillshade',
          source: 'hillshade-dem',
          paint: {
            'hillshade-illumination-direction': 315,
            'hillshade-exaggeration': 0.35,
            'hillshade-shadow-color': '#5a5042',
            'hillshade-highlight-color': '#ffffff',
            'hillshade-accent-color': '#000000',
          },
        },
        firstSymbolLayerId(map),
      )
      // muted atmosphere for the deep-pitch horizon
      try {
        map.setSky({
          'sky-color': '#bcd8f0',
          'horizon-color': '#e8eef2',
          'fog-color': '#f2f4f6',
          'sky-horizon-blend': 0.6,
          'horizon-fog-blend': 0.7,
          'fog-ground-blend': 0.85,
        })
      } catch {
        /* sky spec unavailable — cosmetic only */
      }
      if (modeRef.current === '3d') {
        map.setTerrain({ source: 'terrain-dem', exaggeration: 1.0 })
      }

      // ---- 3D splat pyramid + picking ----
      const intersector = new SpatialIntersector()
      void intersector.load(TILES_BASE)
      intersectorRef.current = intersector
      try {
        const splats = new SplatRenderLayer('palisades-splats', TILES_BASE, intersector)
        splatLayerRef.current = splats
        map.addLayer(splats)
        splats.setEnabled(modeRef.current === '3d')
        // E2E/debug handle (custom layers are invisible to map.getLayer in v5)
        ;(window as unknown as { __splats?: SplatRenderLayer }).__splats = splats
      } catch (e) {
        // the 3D layer must never take down the 2D tracker
        console.error('splat layer failed to initialize:', e)
      }

      onMapReady(map)
    })

    const ro = new ResizeObserver(() => map.resize())
    ro.observe(containerRef.current)
    return () => {
      ro.disconnect()
      map.remove()
      mapRef.current = null
      loadedRef.current = false
      splatLayerRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ---- mode switching: terrain + splats + camera posture ----
  useEffect(() => {
    const map = mapRef.current
    if (!map || !loadedRef.current) return
    if (mode === '3d') {
      if (map.getSource('terrain-dem')) {
        map.setTerrain({ source: 'terrain-dem', exaggeration: 1.0 })
      }
      splatLayerRef.current?.setEnabled(true)
      map.easeTo({ pitch: 62, duration: 900 })
    } else {
      map.setTerrain(null)
      splatLayerRef.current?.setEnabled(false)
      map.easeTo({ pitch: 0, bearing: 0, duration: 900 })
    }
  }, [mode])

  // ---- ground mode: map ↔ current-conditions imagery ----
  useEffect(() => {
    const map = mapRef.current
    if (!map || !loadedRef.current || !map.getLayer('ground-imagery')) return
    for (const id of ['ground-imagery', 'ground-imagery-world']) {
      if (map.getLayer(id)) {
        map.setLayoutProperty(id, 'visibility', ground === 'sat' ? 'visible' : 'none')
      }
    }
    // over imagery the score fills read better slightly lighter
    if (map.getLayer('parcel-fill')) {
      map.setPaintProperty('parcel-fill', 'fill-opacity', [
        'case',
        ['boolean', ['feature-state', 'hover'], false],
        0.92,
        ground === 'sat' ? 0.45 : 0.55,
      ] as never)
    }
  }, [ground])

  // ---- parcel source/layers ----
  useEffect(() => {
    const map = mapRef.current
    if (!map || !parcels) return

    const install = () => {
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
            0.92,
            0.55,
          ] as never,
        },
      })
      map.addLayer({
        id: 'parcel-line',
        type: 'line',
        source: 'parcels',
        paint: {
          'line-color': scorePaintExpression() as never,
          'line-width': ['interpolate', ['linear'], ['zoom'], 13, 0.4, 16, 1.6] as never,
          'line-opacity': 0.9,
        },
      })
      map.addLayer({
        id: 'parcel-selected',
        type: 'line',
        source: 'parcels',
        filter: ['==', ['get', 'apn'], ''],
        paint: { 'line-color': '#1d4ed8', 'line-width': 3.5 },
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

      // click routing: in 3D, ray-pick the building prisms first; the draped
      // parcel polygons are the fallback (and the 2D path)
      map.on('click', (e) => {
        if (modeRef.current === '3d' && intersectorRef.current?.ready) {
          const hit = intersectorRef.current.pick(map, e.point)
          if (hit) {
            onSelect(hit.apn)
            return
          }
        }
        const hits = map.queryRenderedFeatures(e.point, { layers: ['parcel-fill'] })
        onSelect(hits.length ? String(hits[0].properties.apn) : null)
      })
    }

    if (loadedRef.current) install()
    else map.once('load', install)
  }, [parcels, onSelect])

  // selection highlight
  useEffect(() => {
    const map = mapRef.current
    if (!map || !loadedRef.current || !map.getLayer('parcel-selected')) return
    map.setFilter('parcel-selected', ['==', ['get', 'apn'], selectedApn ?? ''])
  }, [selectedApn])

  return <div ref={containerRef} className="map-container" />
}

function firstSymbolLayerId(map: MLMap): string | undefined {
  for (const layer of map.getStyle().layers ?? []) {
    if (layer.type === 'symbol') return layer.id
  }
  return undefined
}
