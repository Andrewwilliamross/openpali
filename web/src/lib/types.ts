// Mirrors the corrected pipeline artifact contract (lane signals + milestone
// facts + typed observations). The retired 0-100 score / 0-5 stage ladder /
// heuristic ETA are gone and must not reappear in any public surface.
import type { Polygon, MultiPolygon } from 'geojson'

export type Jurisdiction = 'LA' | 'COUNTY' | 'MALIBU'
export type StructType = 'SFR' | 'MFR' | 'COM' | 'OTH'

export type LaneSignal =
  | 'no_public_evidence'
  | 'activity_scheduled'
  | 'activity_attempted'
  | 'in_progress'
  | 'milestone_reached'
  | 'conflicting'

export type LaneName =
  | 'cleanup'
  | 'design_review'
  | 'permitting'
  | 'construction'
  | 'occupancy'

export interface ParcelProps {
  apn: string
  address: string
  neighborhood: string
  jurisdiction: Jurisdiction
  struct: StructType
  last_evidence: string | null
  lane_cleanup: LaneSignal
  lane_design: LaneSignal
  lane_permit: LaneSignal
  lane_constr: LaneSignal
  lane_occup: LaneSignal
  cleanup_complete: boolean
  plan_check_approved: boolean
  application_submitted: boolean
  permit_issued: boolean
  construction_evidence: boolean
  cofo_issued: boolean
}

export type ObservationStatus =
  | 'scheduled'
  | 'attempted'
  | 'failed'
  | 'passed'
  | 'canceled'
  | 'issued'
  | 'accepted'
  | 'observed'
  | 'agency_reported'
  | 'inferred'
  | 'retracted'
  | 'conflicting'
  | 'unavailable'
  | 'unknown'

export interface OccurrenceTime {
  kind: 'exact' | 'interval' | 'unknown'
  date?: string
  earliest?: string | null
  latest?: string | null
}

export interface Observation {
  observation_id: string
  subject: { type: string; id: string }
  lane: LaneName | null
  event_type: string
  status: ObservationStatus
  occurred: OccurrenceTime
  observed_at: string
  source_record: { source_id: string; native_key: string; payload_sha256?: string | null }
  policy_version: string
  label: string
  related_subjects: { type: string; id: string }[]
  detail: Record<string, string>
}

export interface LaneProjection {
  lane: LaneName
  signal: LaneSignal
  reached_milestones: string[]
  evidence: string[]
  in_progress: string[]
  scheduled_or_attempted: string[]
  conflicting: string[]
  policy_version: string
}

export interface ParcelLanes {
  policy_version: string
  lanes: LaneProjection[]
  context: string[]
}

export interface PermitRecord {
  no: string
  type: string
  status: string
  submitted: string | null
  issued: string | null
  valuation: number | null
  url: string | null
  qualification:
    | 'qualifying_rebuild_application'
    | 'rebuild_related_ancillary'
    | 'not_fire_rebuild'
    | 'flag_missing'
    | 'undocumented'
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
  observations: Observation[]
  lanes: ParcelLanes | null
  permits: PermitRecord[]
  lat?: number | null
  lon?: number | null
}

export interface Summary {
  as_of: string
  snapshot_id?: string
  totals: {
    destroyed: number
    cleanup_complete: number
    cleanup_opt_out: number
    application_submitted: number
    plan_check_approved: number
    permit_issued: number
    construction_evidence: number
    construction_inspection_scheduled_only: number
    cofo_issued: number
  }
  weekly: { w: string; submitted: number; issued: number }[]
  baselines: {
    source: string
    as_of: string
    metric: string
    official: number
    ours: number
    drift_pct?: number | null
    ok?: boolean
  }[]
  neighborhoods: {
    name: string
    center: [number, number]
    zoom: number
    destroyed: number
    cleanup_complete: number
    application_submitted: number
    permit_issued: number
    cofo_issued: number
  }[]
  policy_versions?: Record<string, string>
}

export type DetailsIndex = Record<string, ParcelDetail>

export interface ParcelFeature {
  type: 'Feature'
  properties: ParcelProps
  geometry: Polygon | MultiPolygon
}

export interface ParcelCollection {
  type: 'FeatureCollection'
  snapshot_id?: string
  features: ParcelFeature[]
}
