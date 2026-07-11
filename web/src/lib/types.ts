// Mirrors Docs/initialbuild_docs/ARTIFACTS.md — the prototype pipeline/frontend contract.
import type { Polygon, MultiPolygon } from 'geojson'

export type Jurisdiction = 'LA' | 'COUNTY' | 'MALIBU'
export type StructType = 'SFR' | 'MFR' | 'COM' | 'OTH'

export interface ParcelProps {
  apn: string
  address: string
  neighborhood: string
  jurisdiction: Jurisdiction
  struct: StructType
  stage: 0 | 1 | 2 | 3 | 4 | 5
  stage_label: string
  score: number
  last_event: string | null
}

export interface TimelineEvent {
  date: string
  kind:
    | 'destroyed'
    | 'debris_cleared'
    | 'permit_submitted'
    | 'permit_issued'
    | 'inspection'
    | 'cofo'
  label: string
  ref?: string
}

export interface PermitRecord {
  no: string
  type: string
  status: string
  submitted: string | null
  issued: string | null
  valuation: number | null
  url: string | null
}

export interface ParcelDetail {
  address: string
  pre_fire: {
    use: string | null
    year_built: number | null
    sqft: number | null
    beds: number | null
    baths: number | null
    units: number | null
  }
  events: TimelineEvent[]
  permits: PermitRecord[]
  est_completion: string | null
  score: number
  score_explain: string
  lat?: number | null
  lon?: number | null
}

export interface Summary {
  as_of: string
  totals: {
    destroyed: number
    cleared: number
    plan_check: number
    permitted: number
    under_construction: number
    complete: number
  }
  weekly: { w: string; submitted: number; issued: number }[]
  baselines: {
    source: string
    as_of: string
    metric: string
    official: number
    ours: number
  }[]
  neighborhoods: {
    name: string
    center: [number, number]
    zoom: number
    destroyed: number
    permitted: number
    under_construction: number
    complete: number
  }[]
}

export type DetailsIndex = Record<string, ParcelDetail>

export interface ParcelFeature {
  type: 'Feature'
  properties: ParcelProps
  geometry: Polygon | MultiPolygon
}

export interface ParcelCollection {
  type: 'FeatureCollection'
  features: ParcelFeature[]
}
