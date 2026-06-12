import { useCallback, useEffect, useRef } from 'react'
import maplibregl, { Map as MLMap, MapMouseEvent } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import type { ParcelCollection } from '../lib/types'
import { scorePaintExpression } from '../lib/colors'
// Type-only imports are erased at build time: the renderer subsystem itself
// is code-split and fetched via import('./spatial/renderer3d') on 3D entry
// (ROADMAP D10 / PR3). Never import its values statically here.
import type { SplatRenderLayer } from './spatial/SplatRenderLayer'
import type { SpatialIntersector } from './spatial/spatial_intersector'

type Renderer3DModule = typeof import('./spatial/renderer3d')

const BASEMAP = 'https://tiles.openfreemap.org/styles/positron'
const PALISADES_CENTER: [number, number] = [-118.5295, 34.0465]
const TILES_BASE = `${import.meta.env.BASE_URL}tiles/palisades`

// AWS Open Data terrain tiles (Mapzen terrarium). maxzoom 15 is mandatory —
// z16 does not exist upstream and must overzoom, not 404.
const DEM_TILES = 'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png'
const DEM_ATTRIBUTION = 'Terrain: USGS 3DEP/SRTM via Mapzen terrain tiles (AWS Open Data)'

// Ground imagery, two stacked sources:
// 1. PRIMARY — LA County LARIAC7 POST-FIRE ortho (flown October 2025), the
//    newest public capture of actual ground conditions: cleared lots, debris
//    pads, and early reconstruction. Served as a public WMTS by the county's
//    vendor (found inside the county's own Road-to-Recovery 3D scene; live to
//    z21 ≈ 7 cm/px). Standard XYZ ({level}/{col}/{row} = z/x/y).
// 2. FALLBACK — Esri World Imagery (current release) outside the LARIAC7
//    flight footprint, so the world doesn't go blank at the coverage edge.
//    NOTE: the world mosaic over the Palisades still shows PRE-fire structures
//    (Wayback release dates are publish dates, not capture dates).
const LARIAC7_TILES =
  'https://svc.pictometry.com/Image/BCC27E3E-766E-CE0B-7D11-AA4760AC43ED/wmts/PICT-LARIAC7--YRwyJETYPH/default/GoogleMapsCompatible/{z}/{x}/{y}.png'
// LARIAC7 WMTS advertised extent (EPSG:3857) → WGS84 bounds for the source
const LARIAC7_BOUNDS: [number, number, number, number] =
  [-118.7281, 33.9275, -117.9640, 34.2096]
const LARIAC7_ATTRIBUTION =
  'Imagery: LA County LARIAC7 Post-Fire Ortho (Oct 2025) © EagleView/Pictometry'
const WORLD_IMAGERY_TILES =
  'https://wayback.maptiles.arcgis.com/arcgis/rest/services/world_imagery/wmts/1.0.0/default028mm/mapserver/tile/10842/{z}/{y}/{x}'
const WORLD_IMAGERY_ATTRIBUTION =
  'Esri World Imagery — Esri, Vantor, Earthstar Geographics'

export type ViewMode = '2d' | '3d'
export type GroundMode = 'map' | 'sat'
// Lifecycle of the lazily fetched 3D chunk; 'idle' = never requested (2D-only
// sessions stay here and ship zero renderer bytes).
export type SpatialStatus = 'idle' | 'loading' | 'ready' | 'error'

interface Props {
  parcels: ParcelCollection | null
  selectedApn: string | null
  mode: ViewMode
  ground: GroundMode
  onSelect: (apn: string | null) => void
  onMapReady: (map: MLMap) => void
  onSpatialStatus?: (status: SpatialStatus) => void
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

export default function MapView({
  parcels,
  selectedApn,
  mode,
  ground,
  onSelect,
  onMapReady,
  onSpatialStatus,
}: Props) {
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
  const onSpatialStatusRef = useRef(onSpatialStatus)
  useEffect(() => {
    onSpatialStatusRef.current = onSpatialStatus
  })
  // cached promise for the code-split renderer chunk (cleared on failure so
  // a retry issues a fresh network request instead of replaying the rejection)
  const rendererModuleRef = useRef<Promise<Renderer3DModule> | null>(null)
  // one-shot guard mirroring the old load-time try/catch: set after the
  // install attempt, success or not, so we never double-add the layer
  const spatialInstalledRef = useRef(false)

  const loadRendererModule = useCallback((): Promise<Renderer3DModule> => {
    if (!rendererModuleRef.current) {
      onSpatialStatusRef.current?.('loading')
      rendererModuleRef.current = import('./spatial/renderer3d').catch((err: unknown) => {
        rendererModuleRef.current = null
        throw err
      })
    }
    return rendererModuleRef.current
  }, [])

  // Fetch the 3D chunk (idempotent) and, once the map style is loaded,
  // install the splat pyramid + ray-picking exactly as the old eager path
  // did. Safe to call before map 'load': the load handler re-invokes it and
  // the cached module promise resolves instantly.
  const ensureSpatial = useCallback(
    (map: MLMap) => {
      if (spatialInstalledRef.current) return
      loadRendererModule()
        .then((mod) => {
          if (mapRef.current !== map || !loadedRef.current) return
          if (spatialInstalledRef.current) return
          spatialInstalledRef.current = true

          // ---- 3D splat pyramid + picking ----
          const intersector = new mod.SpatialIntersector()
          void intersector.load(TILES_BASE)
          intersectorRef.current = intersector
          try {
            const splats = new mod.SplatRenderLayer('palisades-splats', TILES_BASE, intersector)
            splatLayerRef.current = splats
            map.addLayer(splats)
            splats.setEnabled(modeRef.current === '3d')
            // E2E/debug handle (custom layers are invisible to map.getLayer in v5)
            ;(window as unknown as { __splats?: SplatRenderLayer }).__splats = splats
          } catch (e) {
            // the 3D layer must never take down the 2D tracker; terrain-only
            // 3D still works, so this is not surfaced as a chunk failure
            console.error('splat layer failed to initialize:', e)
          }
          onSpatialStatusRef.current?.('ready')
        })
        .catch((err: unknown) => {
          // offline / flaky connection: no white screen — the caller reverts
          // the toggle and offers a retry (which re-fetches the chunk)
          console.error('3D renderer chunk failed to load:', err)
          if (mapRef.current === map) onSpatialStatusRef.current?.('error')
        })
    },
    [loadRendererModule],
  )

  // 3D-only DEM source: created on first 3D entry, never in 2D-only sessions
  const ensureTerrain = useCallback((map: MLMap) => {
    if (!map.getSource('terrain-dem')) {
      map.addSource('terrain-dem', demSource())
    }
    map.setTerrain({ source: 'terrain-dem', exaggeration: 1.0 })
  }, [])

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

    // starting in 3D: fetch the renderer chunk in parallel with the style
    // load (install waits for 'load' below). 2D starts fetch nothing.
    if (modeRef.current === '3d') ensureSpatial(map)

    map.on('load', () => {
      loadedRef.current = true

      // ---- hillshade DEM (2D feature too; terrain-dem is added lazily on
      // 3D entry — separate source instances, per ML guidance) ----
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
        tiles: [LARIAC7_TILES],
        tileSize: 256,
        maxzoom: 21,
        bounds: LARIAC7_BOUNDS,
        attribution: LARIAC7_ATTRIBUTION,
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
      // 3D-only pieces (terrain + splat renderer) are lazy: nothing spatial
      // initializes unless the session actually enters 3D
      if (modeRef.current === '3d') {
        ensureTerrain(map)
        ensureSpatial(map)
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
      intersectorRef.current = null
      spatialInstalledRef.current = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ---- mode switching: terrain + splats + camera posture ----
  useEffect(() => {
    const map = mapRef.current
    if (!map || !loadedRef.current) return
    if (mode === '3d') {
      ensureTerrain(map)
      // first entry kicks off the chunk fetch; once installed it's a no-op
      // and setEnabled below drives the already-resident layer
      ensureSpatial(map)
      splatLayerRef.current?.setEnabled(true)
      map.easeTo({ pitch: 62, duration: 900 })
    } else {
      map.setTerrain(null)
      splatLayerRef.current?.setEnabled(false)
      map.easeTo({ pitch: 0, bearing: 0, duration: 900 })
    }
  }, [mode, ensureTerrain, ensureSpatial])

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
