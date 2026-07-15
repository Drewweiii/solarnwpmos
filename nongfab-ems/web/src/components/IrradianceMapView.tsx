// The actual MapLibre canvas for Feature E - not unit-testable in jsdom (no
// WebGL context), so this file has no companion test; correctness is
// verified live (see web/README.md "Verified live"), same pattern as
// Solar3DScene.tsx. IrradianceMapPage wires data/controls and mocks this
// component in its own tests.

import type { FeatureCollection, Point } from 'geojson'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { useEffect, useRef, useState } from 'react'
import type { IrradianceGridPoint, ZonePin } from '../lib/types'

// A self-contained blank style (no external tile/glyph/sprite fetches) - no
// basemap-provider API key/ToS decision has been made for this dashboard
// yet (see web/README.md "Known gaps"). The irradiance overlay and zone
// pins are functionally complete without real street/satellite tiles
// underneath; swapping in a real basemap style URL is a follow-up, not a
// redesign of this component.
const BLANK_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {},
  layers: [{ id: 'background', type: 'background', paint: { 'background-color': '#0b1220' } }],
}

const GRID_SOURCE_ID = 'irradiance-grid'
const ZONES_SOURCE_ID = 'zone-pins'
const ZONES_LABEL_LAYER_ID = 'zone-pins-label'
const BOUNDARY_SOURCE_ID = 'zone-boundaries'
const BOUNDARY_FILL_LAYER_ID = 'zone-boundaries-fill'
const BOUNDARY_LINE_LAYER_ID = 'zone-boundaries-line'

interface ZonePinProps {
  id: string
  name_full: string
  ac_capacity_kw: number
  simulated: boolean
  lat: number
  lon: number
  ghi_w_m2: number
  cloud_factor: number
  estimated_ac_kw: number
  plant_factor: number
}

function gridToGeoJSON(points: IrradianceGridPoint[]): FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: points.map((p) => ({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [p.lon, p.lat] },
      properties: { ghi_w_m2: p.ghi_w_m2, cloud_factor: p.cloud_factor },
    })),
  }
}

function zonesToGeoJSON(zones: ZonePin[]): FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: zones.map((z) => ({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [z.lon, z.lat] },
      properties: {
        id: z.id, name_full: z.name_full, ac_capacity_kw: z.ac_capacity_kw, simulated: z.simulated,
        lat: z.lat, lon: z.lon, ghi_w_m2: z.ghi_w_m2, cloud_factor: z.cloud_factor,
        estimated_ac_kw: z.estimated_ac_kw, plant_factor: z.plant_factor,
      } satisfies ZonePinProps,
    })),
  }
}

function boundariesToGeoJSON(zones: ZonePin[]): FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: zones.map((z) => ({
      type: 'Feature',
      geometry: { type: 'Polygon', coordinates: [z.boundary.map((p) => [p.lon, p.lat])] },
      properties: { id: z.id },
    })),
  }
}

function popupHtml(props: ZonePinProps): string {
  return `
    <strong>${props.id}</strong> - ${props.name_full}${props.simulated ? ' <em>(simulated)</em>' : ''}<br/>
    lat/lon: ${props.lat.toFixed(5)}, ${props.lon.toFixed(5)}<br/>
    installed: ${props.ac_capacity_kw} kW<br/>
    estimated output: ${props.estimated_ac_kw.toFixed(1)} kW<br/>
    plant factor: ${(props.plant_factor * 100).toFixed(1)}%<br/>
    est. irradiance: ${props.ghi_w_m2.toFixed(0)} W/m&sup2;<br/>
    cloud factor: ${(props.cloud_factor * 100).toFixed(0)}%
  `
}

interface IrradianceMapViewProps {
  grid: IrradianceGridPoint[]
  zones: ZonePin[]
  showIrradiance: boolean
  showZones: boolean
  showBoundary: boolean
}

export function IrradianceMapView({ grid, zones, showIrradiance, showZones, showBoundary }: IrradianceMapViewProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  // Layers are added asynchronously inside the map's 'load' event, so the
  // visibility effect below needs to know once they actually exist - without
  // this, a toggle clicked before 'load' fires would silently no-op (found
  // live: see web/README.md "Verified live").
  const [layersReady, setLayersReady] = useState(false)

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return
    const centerLat = zones.length ? zones.reduce((s, z) => s + z.lat, 0) / zones.length : 12.71
    const centerLon = zones.length ? zones.reduce((s, z) => s + z.lon, 0) / zones.length : 101.15

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: BLANK_STYLE,
      center: [centerLon, centerLat],
      zoom: 13,
      attributionControl: false,
    })
    map.addControl(new maplibregl.NavigationControl(), 'top-right')

    map.on('load', () => {
      map.addSource(BOUNDARY_SOURCE_ID, { type: 'geojson', data: boundariesToGeoJSON(zones) })
      map.addLayer({
        id: BOUNDARY_FILL_LAYER_ID, type: 'fill', source: BOUNDARY_SOURCE_ID,
        paint: { 'fill-color': '#38bdf8', 'fill-opacity': 0.08 },
      })
      map.addLayer({
        id: BOUNDARY_LINE_LAYER_ID, type: 'line', source: BOUNDARY_SOURCE_ID,
        paint: { 'line-color': '#38bdf8', 'line-width': 1.5, 'line-dasharray': [2, 1] },
      })

      map.addSource(GRID_SOURCE_ID, { type: 'geojson', data: gridToGeoJSON(grid) })
      map.addLayer({
        id: GRID_SOURCE_ID,
        type: 'circle',
        source: GRID_SOURCE_ID,
        paint: {
          'circle-radius': 22,
          'circle-blur': 1,
          'circle-opacity': 0.55,
          'circle-color': [
            'interpolate',
            ['linear'],
            ['get', 'ghi_w_m2'],
            0, '#1e3a8a',
            300, '#2563eb',
            600, '#f59e0b',
            1000, '#ef4444',
          ],
        },
      })

      map.addSource(ZONES_SOURCE_ID, { type: 'geojson', data: zonesToGeoJSON(zones) })
      map.addLayer({
        id: ZONES_SOURCE_ID,
        type: 'circle',
        source: ZONES_SOURCE_ID,
        paint: { 'circle-radius': 8, 'circle-color': '#ffffff', 'circle-stroke-width': 2, 'circle-stroke-color': '#111827' },
      })
      map.addLayer({
        id: ZONES_LABEL_LAYER_ID,
        type: 'symbol',
        source: ZONES_SOURCE_ID,
        layout: { 'text-field': ['get', 'id'], 'text-size': 12, 'text-offset': [0, 1.4] },
        paint: { 'text-color': '#ffffff', 'text-halo-color': '#111827', 'text-halo-width': 1 },
      })

      map.on('click', ZONES_SOURCE_ID, (e) => {
        const feature = e.features?.[0]
        if (!feature) return
        const coords = (feature.geometry as Point).coordinates.slice() as [number, number]
        const props = feature.properties as unknown as ZonePinProps
        new maplibregl.Popup().setLngLat(coords).setHTML(popupHtml(props)).addTo(map)
      })
      map.on('mouseenter', ZONES_SOURCE_ID, () => {
        map.getCanvas().style.cursor = 'pointer'
      })
      map.on('mouseleave', ZONES_SOURCE_ID, () => {
        map.getCanvas().style.cursor = ''
      })

      setLayersReady(true)
    })

    mapRef.current = map
    return () => {
      map.remove()
      mapRef.current = null
    }
    // Map is created once on mount; grid/zones/visibility updates are
    // applied by the effects below instead of tearing the map down.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !map.isStyleLoaded()) return
    const source = map.getSource(GRID_SOURCE_ID) as maplibregl.GeoJSONSource | undefined
    source?.setData(gridToGeoJSON(grid))
  }, [grid])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !map.isStyleLoaded()) return
    const zonesSource = map.getSource(ZONES_SOURCE_ID) as maplibregl.GeoJSONSource | undefined
    zonesSource?.setData(zonesToGeoJSON(zones))
    const boundarySource = map.getSource(BOUNDARY_SOURCE_ID) as maplibregl.GeoJSONSource | undefined
    boundarySource?.setData(boundariesToGeoJSON(zones))
  }, [zones])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !layersReady) return
    const setVisibility = (id: string, visible: boolean) => {
      if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', visible ? 'visible' : 'none')
    }
    setVisibility(GRID_SOURCE_ID, showIrradiance)
    setVisibility(ZONES_SOURCE_ID, showZones)
    setVisibility(ZONES_LABEL_LAYER_ID, showZones)
    setVisibility(BOUNDARY_FILL_LAYER_ID, showBoundary)
    setVisibility(BOUNDARY_LINE_LAYER_ID, showBoundary)
  }, [showIrradiance, showZones, showBoundary, layersReady])

  return <div ref={containerRef} className="irradiance-map-canvas" data-testid="irradiance-map-canvas" />
}
