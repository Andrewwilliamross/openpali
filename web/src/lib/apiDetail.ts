// Release-qualified property evidence (FRONTEND-001): the card's lanes and
// observation timeline come from the pinned release's API when reachable,
// with the pipeline-generated static bundle as offline/LKG fallback. Permits
// enrichment (portal links, valuations) stays from the static bundle until
// the API exposes a permits view.

import type {
  LaneName,
  LaneSignal,
  Observation,
  ObservationStatus,
  OccurrenceTime,
  ParcelDetail,
  ParcelLanes,
} from './types'
import { fetchPostfireSources } from './postfire'

interface ApiOccurrence {
  kind: string
  date?: string | null
  earliest?: string | null
  latest?: string | null
}

interface ApiObservation {
  observation_id: string
  subject_type: string
  subject_id: string
  lane: string | null
  event_type: string
  status: string
  occurred: ApiOccurrence
  observed_at: string
  source_id: string
  record_version_id: string | null
  policy_version: string
  label: string
  related_subjects: { type: string; id: string }[]
  detail: Record<string, string>
  retracted: boolean
  retraction_reason: string | null
}

interface ApiPropertyDetail {
  property_id: string
  apn: string
  address: string | null
  lane_signals: Record<string, string>
  projection_policy_version: string
  pre_fire: Record<string, unknown>
  center: [number, number] | null
}

function mapObservation(o: ApiObservation): Observation {
  return {
    observation_id: o.observation_id,
    subject: { type: o.subject_type, id: o.subject_id },
    lane: (o.lane as LaneName) ?? null,
    event_type: o.event_type,
    status: o.status as ObservationStatus,
    occurred: {
      kind: o.occurred.kind as OccurrenceTime['kind'],
      date: o.occurred.date ?? undefined,
      earliest: o.occurred.earliest ?? null,
      latest: o.occurred.latest ?? null,
    },
    observed_at: o.observed_at,
    source_record: { source_id: o.source_id, native_key: o.record_version_id ?? '' },
    policy_version: o.policy_version,
    label: o.retracted && o.retraction_reason
      ? `${o.label} (retracted: ${o.retraction_reason})`
      : o.label,
    related_subjects: o.related_subjects,
    detail: o.detail,
  }
}

function num(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null
}

function str(v: unknown): string | null {
  return typeof v === 'string' && v ? v : null
}

/** Fetch + map the release-qualified detail; null when the API is absent. */
export async function fetchApiDetail(apn: string): Promise<ParcelDetail | null> {
  const sources = await fetchPostfireSources()
  if (!sources) return null
  const base = `/v1/releases/${sources.releaseId}/properties/${apn}`
  try {
    const detailResp = await fetch(base)
    if (!detailResp.ok) return null
    const d = (await detailResp.json()) as ApiPropertyDetail

    const observations: Observation[] = []
    let cursor: string | null = null
    for (let pageN = 0; pageN < 6; pageN++) {
      const url: string = `${base}/observations?limit=100${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}`
      const page = await fetch(url)
      if (!page.ok) break
      const body = (await page.json()) as { items: ApiObservation[]; next_cursor: string | null }
      observations.push(...body.items.map(mapObservation))
      cursor = body.next_cursor
      if (!cursor) break
    }

    const lanes: ParcelLanes = {
      policy_version: d.projection_policy_version,
      lanes: Object.entries(d.lane_signals).map(([lane, signal]) => ({
        lane: lane as LaneName,
        signal: signal as LaneSignal,
        reached_milestones: [],
        evidence: [],
        in_progress: [],
        scheduled_or_attempted: [],
        conflicting: [],
        policy_version: d.projection_policy_version,
      })),
      context: [`release ${sources.releaseId}`],
    }

    const pf = d.pre_fire ?? {}
    return {
      address: d.address ?? '',
      pre_fire: {
        use: str(pf.use ?? pf.use_type),
        year_built: num(pf.year_built),
        sqft: num(pf.sqft),
        beds: num(pf.beds),
        baths: num(pf.baths),
        units: num(pf.units),
      },
      observations,
      lanes,
      permits: [], // enrichment merged from the static bundle by the card
      lon: d.center?.[0] ?? null,
      lat: d.center?.[1] ?? null,
    }
  } catch {
    return null
  }
}
