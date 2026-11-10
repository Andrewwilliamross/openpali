import type { Feature, FeatureCollection, MultiPolygon, Polygon } from 'geojson'

/** Properties of `artifacts/parcels.geojson` in an evidence release. */
export interface ParcelProps {
  apn: string
  address: string
  /** agency fire-damage assessment; 'unknown' is not 'undamaged' */
  damage: 'destroyed' | 'unknown' | (string & {})
  /** highest agency-reported recovery milestone (RECOVERY_STAGE ladder) */
  stage: string
}

export type ParcelFeature = Feature<Polygon | MultiPolygon, ParcelProps>
export type ParcelCollection = FeatureCollection<Polygon | MultiPolygon, ParcelProps>
