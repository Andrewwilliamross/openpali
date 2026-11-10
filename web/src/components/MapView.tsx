import { useCallback, useEffect, useMemo, useRef } from 'react'
import maplibregl, { Map as MLMap, MapMouseEvent } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import type { MapData } from '../lib/types'
import { scorePaintExpression, scoreRgb } from '../lib/colors'
// Type-only import, erased at build time: the 3D renderer is code-split and
// fetched via import('./scene/BuildingLayer') in parallel with the style.
import type { BuildingLayer, ParcelStyle } from './scene/BuildingLayer'
import { installTerrainProtocol, NOT_BAKED, TERRAIN_TILES } from './scene/terrainProtocol'

const BASEMAP = 'https://tiles.openfreemap.org/styles/positron'
const PALISADES_CENTER: [number, number] = [-118.5295, 34.0465]
const SCENE_BASE = `${import.meta.env.BASE_URL}scene`
export const VIEW_PITCH = 60

// Elevation comes through the scene's terrain protocol: USGS post-fire lidar
// where the scene build baked it (to zoom 16, 2 m), Mapzen terrain tiles (AWS
// Open Data, to zoom 15) everywhere else. Structures are registered against
// this same surface at build time.
const DEM_MAXZOOM = 16
const DEM_ATTRIBUTION =
  'Terrain: USGS 2025 post-wildfire lidar (preliminary); USGS 3DEP/SRTM via Mapzen terrain tiles (AWS Open Data)'

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
const STRUCTURES_ATTRIBUTION =
  'Structures: LA County 2023 building model (non-authoritative); destroyed structures outlined in their lot’s rebuild score'

// feature properties written by the release build (parcels.geojson)
const SCORE_PROPERTY = 'score'
const VISUAL_WEIGHT_PROPERTY = 'weight'

interface Props {
  data: MapData | null
  selectedApn: string | null
  onSelect: (apn: string | null) => void
  onMapReady: (map: MLMap) => void
}

function demSource(): maplibregl.RasterDEMSourceSpecification {
  return {
    type: 'raster-dem',
    encoding: 'terrarium',
    tiles: [TERRAIN_TILES],
    tileSize: 256,
    minzoom: 0,
    maxzoom: DEM_MAXZOOM,
    attribution: DEM_ATTRIBUTION,
  }
}

export default function MapView({ data, selectedApn, onSelect, onMapReady }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MLMap | null>(null)
  const hoveredRef = useRef<string | number | null>(null)
  const loadedRef = useRef(false)
  const buildingsRef = useRef<BuildingLayer | null>(null)
  const parcelStylesRef = useRef<Map<string, ParcelStyle> | null>(null)
  const selectedApnRef = useRef(selectedApn)
  const onSelectRef = useRef(onSelect)
  const onMapReadyRef = useRef(onMapReady)
  useEffect(() => {
    onSelectRef.current = onSelect
    onMapReadyRef.current = onMapReady
  })

  // what the 3D structures need to know about each lot
  const parcelStyles = useMemo<Map<string, ParcelStyle> | null>(() => {
    if (!data) return null
    const styles = new Map<string, ParcelStyle>()
    for (const parcel of data.parcels) {
      styles.set(parcel.apn, {
        color: parcel.score === null ? null : scoreRgb(parcel.score),
        destroyed: parcel.destroyed,
      })
    }
    return styles
  }, [data])
  const parcelsUrl = data?.parcelsUrl ?? null

  // Fetch the 3D chunk and install the building meshes. The 3D layer must
  // never take down the map: every failure leaves terrain, imagery and the
  // draped score fills working.
  const installBuildings = useCallback((map: MLMap) => {
    import('./scene/BuildingLayer')
      .then((mod) => {
        if (mapRef.current !== map || !loadedRef.current || buildingsRef.current) return
        const buildings = new mod.BuildingLayer('palisades-buildings', SCENE_BASE, {
          aerialTemplate: GROUND26_TILES,
        })
        buildingsRef.current = buildings
        map.addLayer(buildings)
        if (parcelStylesRef.current) buildings.setParcels(parcelStylesRef.current)
        buildings.select(selectedApnRef.current)
        // debug handle (custom layers are invisible to map.getLayer in v5)
        ;(window as unknown as { __buildings?: BuildingLayer }).__buildings = buildings
      })
      .catch((err: unknown) => {
        console.error('3D structures failed to initialize:', err)
      })
  }, [])

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return
    installTerrainProtocol(SCENE_BASE)
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: BASEMAP,
      center: PALISADES_CENTER,
      zoom: 14.2,
      pitch: VIEW_PITCH,
      bearing: -12,
      maxPitch: 85,
      minZoom: 10,
      maxZoom: 19,
      attributionControl: false,
    })
    // Source credits sit behind the OpenPali mark and start collapsed. MapLibre
    // opens a compact control the first time it applies the compact class, so
    // the class is applied here first.
    map.addControl(
      new maplibregl.AttributionControl({ compact: true, customAttribution: STRUCTURES_ATTRIBUTION }),
      'bottom-right',
    )
    const credits = map.getContainer().querySelector('.maplibregl-ctrl-attrib')
    credits?.classList.add('maplibregl-compact')
    credits?.classList.remove('maplibregl-compact-show')
    credits?.removeAttribute('open')
    credits?.querySelector('summary')?.setAttribute('aria-label', 'Map data sources')
    mapRef.current = map
    ;(window as unknown as { __map?: MLMap }).__map = map
    // One failure is expected and silent: a zoom-16 terrain tile outside the
    // lidar, which MapLibre covers from its zoom-15 parent.
    map.on('error', (event) => {
      if (event.error?.message?.includes(NOT_BAKED)) return
      console.error(event.error)
    })

    map.on('load', () => {
      loadedRef.current = true
      // WebGL context loss: drop 3D work and keep the map usable
      map.getCanvas().addEventListener('webglcontextlost', () => {
        buildingsRef.current?.setEnabled(false)
      })

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
      for (const id of ['ground-imagery-world', 'ground-imagery']) {
        map.addLayer({ id, type: 'raster', source: id }, firstSymbolLayerId(map))
      }
      // hillshade and terrain use separate DEM source instances (ML guidance)
      map.addSource('hillshade-dem', demSource())
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
      map.addSource('terrain-dem', demSource())
      map.setTerrain({ source: 'terrain-dem', exaggeration: 1.0 })
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
      // street labels sit on aerial imagery now: give them a dark halo
      for (const layer of map.getStyle().layers ?? []) {
        if (layer.type !== 'symbol') continue
        map.setPaintProperty(layer.id, 'text-color', '#ffffff')
        map.setPaintProperty(layer.id, 'text-halo-color', 'rgba(15, 20, 25, 0.85)')
        map.setPaintProperty(layer.id, 'text-halo-width', 1.4)
      }

      installBuildings(map)
      onMapReadyRef.current(map)
    })

    const ro = new ResizeObserver(() => map.resize())
    ro.observe(containerRef.current)
    return () => {
      ro.disconnect()
      map.remove()
      mapRef.current = null
      loadedRef.current = false
      buildingsRef.current = null
    }
  }, [installBuildings])

  // ---- score colour and damage for the 3D structures ----
  useEffect(() => {
    parcelStylesRef.current = parcelStyles
    if (parcelStyles) buildingsRef.current?.setParcels(parcelStyles)
  }, [parcelStyles])

  // ---- parcel source/layers ----
  useEffect(() => {
    const map = mapRef.current
    if (!map || !parcelsUrl) return

    const install = () => {
      if (mapRef.current !== map) return
      hoveredRef.current = null
      const existing = map.getSource('parcels') as maplibregl.GeoJSONSource | undefined
      if (existing) {
        existing.setData(parcelsUrl)
        return
      }
      // by URL: MapLibre fetches, parses and tiles the polygons in its worker,
      // so 10,000 lots never pass through the main thread
      map.addSource('parcels', { type: 'geojson', data: parcelsUrl, promoteId: 'apn' })
      const weight = ['coalesce', ['get', VISUAL_WEIGHT_PROPERTY], 1]
      const scored = ['has', SCORE_PROPERTY] as maplibregl.FilterSpecification
      // unscored parcels: an invisible hit area (hover/click) and a quiet outline
      map.addLayer({
        id: 'parcel-hit',
        type: 'fill',
        source: 'parcels',
        paint: { 'fill-color': '#ffffff', 'fill-opacity': 0 },
      })
      map.addLayer({
        id: 'parcel-fill',
        type: 'fill',
        source: 'parcels',
        filter: scored,
        paint: {
          'fill-color': scorePaintExpression(SCORE_PROPERTY) as never,
          'fill-opacity': [
            'case',
            ['boolean', ['feature-state', 'hover'], false],
            0.9,
            // light enough that the structures standing on a lot read clearly
            ['*', 0.34, weight],
          ] as never,
        },
      })
      map.addLayer({
        id: 'parcel-outline',
        type: 'line',
        source: 'parcels',
        filter: ['!', scored] as never,
        minzoom: 15,
        paint: { 'line-color': '#ffffff', 'line-width': 0.6, 'line-opacity': 0.35 },
      })
      map.addLayer({
        id: 'parcel-line',
        type: 'line',
        source: 'parcels',
        filter: scored,
        paint: {
          'line-color': scorePaintExpression(SCORE_PROPERTY) as never,
          'line-width': ['interpolate', ['linear'], ['zoom'], 13, 0.4, 16, 1.6] as never,
          'line-opacity': ['*', 0.8, weight] as never,
        },
      })
      map.addLayer({
        id: 'parcel-selected',
        type: 'line',
        source: 'parcels',
        filter: ['==', ['get', 'apn'], selectedApnRef.current ?? ''],
        paint: { 'line-color': '#ffffff', 'line-width': 3.5 },
      })

      const setHover = (id: string | number | null): void => {
        if (hoveredRef.current === id) return
        if (hoveredRef.current != null)
          map.setFeatureState({ source: 'parcels', id: hoveredRef.current }, { hover: false })
        hoveredRef.current = id
        if (id != null) map.setFeatureState({ source: 'parcels', id }, { hover: true })
      }
      map.on('mousemove', 'parcel-hit', (e: MapMouseEvent) => {
        const f = (e as MapMouseEvent & { features?: maplibregl.MapGeoJSONFeature[] })
          .features?.[0]
        map.getCanvas().style.cursor = f ? 'pointer' : ''
        setHover(f?.id ?? null)
      })
      map.on('mouseleave', 'parcel-hit', () => {
        map.getCanvas().style.cursor = ''
        setHover(null)
      })

      // Click routing: the structure under the cursor wins (a wall hides the
      // lot behind it); the draped parcel polygons are the fallback.
      map.on('click', (e) => {
        const hits = map.queryRenderedFeatures(e.point, { layers: ['parcel-hit'] })
        const parcelApn = hits.length ? String(hits[0].properties.apn) : null
        const buildings = buildingsRef.current
        if (!buildings) {
          onSelectRef.current(parcelApn)
          return
        }
        void buildings.pick(e.point).then((apn) => onSelectRef.current(apn ?? parcelApn))
      })
    }

    if (loadedRef.current) install()
    else map.once('load', install)
  }, [parcelsUrl])

  // selection highlight
  useEffect(() => {
    selectedApnRef.current = selectedApn
    buildingsRef.current?.select(selectedApn)
    const map = mapRef.current
    if (!map || !loadedRef.current || !map.getLayer('parcel-selected')) return
    map.setFilter('parcel-selected', ['==', ['get', 'apn'], selectedApn ?? ''])
  }, [selectedApn])

  return <div ref={containerRef} className="map-container" aria-label="3D map of the Palisades rebuild" />
}

function firstSymbolLayerId(map: MLMap): string | undefined {
  for (const layer of map.getStyle().layers ?? []) {
    if (layer.type === 'symbol') return layer.id
  }
  return undefined
}
