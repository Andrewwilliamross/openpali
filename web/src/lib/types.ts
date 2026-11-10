/** One parcel from the release's `parcel-index.json`. */
export interface ParcelRow {
  apn: string
  address: string
  /** a point on the parcel; null when the release has no geometry for it */
  center: [number, number] | null
  /** agency fire-damage assessment says destroyed ('unknown' is not 'undamaged') */
  destroyed: boolean
  /** 0–100 position of the parcel's highest agency-reported recovery
   *  milestone; null for parcels not assessed as destroyed (not the same as 0) */
  score: number | null
}

export interface MapData {
  /** `parcels.geojson` of the same release; features carry `score` and `weight` */
  parcelsUrl: string
  parcels: ParcelRow[]
}
