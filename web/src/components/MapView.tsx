import { useEffect, useMemo, useRef } from 'react'
import maplibregl, { Map as MLMap, MapMouseEvent } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import type { ParcelCollection } from '../lib/types'
import { scorePaintExpression } from '../lib/colors'
import { geometryAreaM2, largeParcelVisualWeight } from '../lib/parcelPresentation'
import { SplatRenderLayer } from './spatial/SplatRenderLayer'
import { SpatialIntersector } from './spatial/spatial_intersector'
import { resolveTerrainConfig, toDemSource } from '../lib/terrain'
import { TILES_BASE } from '../lib/config'

const BASEMAP = 'https://tiles.openfreemap.org/styles/positron'
const PALISADES_CENTER: [number, number] = [-118.5295, 34.0465]

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
const LAYER_TRANSITION_MS = 220
const VISUAL_WEIGHT_PROPERTY = '__visual_weight'

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

// Terrain DEM is config-driven (see lib/terrain): default AWS terrarium, or the
// in-footprint post-fire DTM when VITE_POSTFIRE_TERRAIN is enabled.
function demSource(): maplibregl.RasterDEMSourceSpecification {
  return toDemSource(resolveTerrainConfig()) as maplibregl.RasterDEMSourceSpecification
}

export default function MapView({ parcels, selectedApn, mode, ground, onSelect, onMapReady }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MLMap | null>(null)
  const hoveredRef = useRef<string | number | null>(null)
  const loadedRef = useRef(false)
  const splatLayerRef = useRef<SplatRenderLayer | null>(null)
  const intersectorRef = useRef<SpatialIntersector | null>(null)
  const modeRef = useRef<ViewMode>(mode)
  const groundRef = useRef<GroundMode>(ground)
  useEffect(() => {
    modeRef.current = mode
  }, [mode])
  useEffect(() => {
    groundRef.current = ground
  }, [ground])
  // The fire footprint includes legitimate acreage parcels (parks, canyons,
  // coastal easements). Keep them interactive and scored, but reduce their
  // visual weight so they do not blanket the lot-level layer at overview zooms.
  const renderedParcels = useMemo<ParcelCollection | null>(() => {
    if (!parcels) return null
    return {
      ...parcels,
      features: parcels.features.map((feature) => ({
        ...feature,
        properties: {
          ...feature.properties,
          [VISUAL_WEIGHT_PROPERTY]: largeParcelVisualWeight(geometryAreaM2(feature.geometry)),
        },
      })),
    }
  }, [parcels])

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
          paint: { 'raster-opacity': groundRef.current === 'sat' ? 1 : 0 },
        },
        firstSymbolLayerId(map),
      )
      map.addLayer(
        {
          id: 'ground-imagery',
          type: 'raster',
          source: 'ground-imagery',
          paint: { 'raster-opacity': groundRef.current === 'sat' ? 1 : 0 },
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
    if (!map || !loadedRef.current) return
    const imageryOpacity = ground === 'sat' ? 1 : 0
    for (const id of ['ground-imagery', 'ground-imagery-world']) {
      if (map.getLayer(id)) {
        map.setPaintProperty(id, 'raster-opacity-transition', {
          duration: LAYER_TRANSITION_MS,
        } as never)
        map.setPaintProperty(id, 'raster-opacity', imageryOpacity)
      }
    }
    // Over imagery the score fills read better slightly lighter. The same
    // transition avoids a one-frame intensity pop when switching ground modes.
    if (map.getLayer('parcel-fill')) {
      map.setPaintProperty('parcel-fill', 'fill-opacity-transition', {
        duration: LAYER_TRANSITION_MS,
      } as never)
      map.setPaintProperty('parcel-fill', 'fill-opacity', parcelFillOpacity(ground) as never)
    }
    if (map.getLayer('parcel-line')) {
      map.setPaintProperty('parcel-line', 'line-opacity-transition', {
        duration: LAYER_TRANSITION_MS,
      } as never)
      map.setPaintProperty('parcel-line', 'line-opacity', parcelLineOpacity(ground) as never)
    }
  }, [ground])

  // ---- parcel source/layers ----
  useEffect(() => {
    const map = mapRef.current
    if (!map || !renderedParcels) return

    const install = () => {
      hoveredRef.current = null
      if (map.getSource('parcels')) {
        ;(map.getSource('parcels') as maplibregl.GeoJSONSource).setData(renderedParcels)
        return
      }
      map.addSource('parcels', { type: 'geojson', data: renderedParcels, promoteId: 'apn' })
      map.addLayer({
        id: 'parcel-fill',
        type: 'fill',
        source: 'parcels',
        paint: {
          'fill-color': scorePaintExpression() as never,
          'fill-opacity': parcelFillOpacity(groundRef.current) as never,
        },
      })
      map.addLayer({
        id: 'parcel-line',
        type: 'line',
        source: 'parcels',
        paint: {
          'line-color': scorePaintExpression() as never,
          'line-width': ['interpolate', ['linear'], ['zoom'], 13, 0.4, 16, 1.6] as never,
          'line-opacity': parcelLineOpacity(groundRef.current) as never,
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
      // parcel polygons are the fallback (and the 2D path). Some spatial
      // assets were generated from a different parcel snapshot, so when both
      // layers resolve a click, prefer the current parcel under the cursor.
      map.on('click', (e) => {
        const hits = map.queryRenderedFeatures(e.point, { layers: ['parcel-fill'] })
        const parcelApn = hits.length ? String(hits[0].properties.apn) : null
        if (modeRef.current === '3d' && intersectorRef.current?.ready) {
          const hit = intersectorRef.current.pick(map, e.point)
          if (hit && (!parcelApn || hit.apn === parcelApn)) {
            onSelect(hit.apn)
            return
          }
        }
        onSelect(parcelApn)
      })
    }

    if (loadedRef.current) install()
    else map.once('load', install)
  }, [renderedParcels, onSelect])

  // selection highlight
  useEffect(() => {
    const map = mapRef.current
    if (!map || !loadedRef.current || !map.getLayer('parcel-selected')) return
    map.setFilter('parcel-selected', ['==', ['get', 'apn'], selectedApn ?? ''])
  }, [selectedApn])

  return <div ref={containerRef} className="map-container" />
}

function parcelFillOpacity(ground: GroundMode): unknown[] {
  return [
    'case',
    ['boolean', ['feature-state', 'hover'], false],
    0.92,
    [
      '*',
      ground === 'sat' ? 0.45 : 0.55,
      ['coalesce', ['get', VISUAL_WEIGHT_PROPERTY], 1],
    ],
  ]
}

function parcelLineOpacity(ground: GroundMode): unknown[] {
  return [
    '*',
    ground === 'sat' ? 0.7 : 0.82,
    ['coalesce', ['get', VISUAL_WEIGHT_PROPERTY], 1],
  ]
}

function firstSymbolLayerId(map: MLMap): string | undefined {
  for (const layer of map.getStyle().layers ?? []) {
    if (layer.type === 'symbol') return layer.id
  }
  return undefined
}
