// Categorical evidence colors. Single source of truth for the MapLibre paint
// expression, the legend, and badges.
//
// The map colors parcels by their MOST ADVANCED *evidenced* milestone — a
// factual category backed by source records, never a 0-100 score, heuristic
// ETA, ranking, or effort/quality judgment. "No permit evidence" means "no
// event in covered public sources", never "the resident has done nothing".

export interface EvidenceCategory {
  key: string
  label: string
  color: string
}

// Ordered least → most advanced *evidenced* milestone. A scheduled inspection
// is activity, not a milestone, and therefore never changes a parcel's color.
export const EVIDENCE_CATEGORIES: EvidenceCategory[] = [
  { key: 'none', label: 'No public evidence', color: '#8c8c93' },
  { key: 'cleanup_complete', label: 'Debris cleared (gov. program)', color: '#b46e5a' },
  { key: 'application_submitted', label: 'Rebuild application', color: '#e0a13c' },
  { key: 'plan_check_approved', label: 'Plans approved', color: '#d3c53a' },
  { key: 'permit_issued', label: 'Permit issued', color: '#7fbf4d' },
  { key: 'construction_evidence', label: 'Construction evidence', color: '#3fa06a' },
  { key: 'cofo_issued', label: 'Certificate of Occupancy', color: '#1b7837' },
]

export const CATEGORY_BY_KEY: Record<string, EvidenceCategory> = Object.fromEntries(
  EVIDENCE_CATEGORIES.map((c) => [c.key, c]),
)

/** Most advanced evidenced milestone for a feature's milestone booleans. */
export function evidenceCategory(props: {
  cleanup_complete?: boolean
  application_submitted?: boolean
  plan_check_approved?: boolean
  permit_issued?: boolean
  construction_evidence?: boolean
  cofo_issued?: boolean
}): EvidenceCategory {
  if (props.cofo_issued) return CATEGORY_BY_KEY.cofo_issued
  if (props.construction_evidence) return CATEGORY_BY_KEY.construction_evidence
  if (props.permit_issued) return CATEGORY_BY_KEY.permit_issued
  if (props.plan_check_approved) return CATEGORY_BY_KEY.plan_check_approved
  if (props.application_submitted) return CATEGORY_BY_KEY.application_submitted
  if (props.cleanup_complete) return CATEGORY_BY_KEY.cleanup_complete
  return CATEGORY_BY_KEY.none
}

/** MapLibre data-driven fill color over the milestone boolean properties. */
export function evidencePaintExpression(): unknown[] {
  return [
    'case',
    ['==', ['get', 'cofo_issued'], true], CATEGORY_BY_KEY.cofo_issued.color,
    ['==', ['get', 'construction_evidence'], true], CATEGORY_BY_KEY.construction_evidence.color,
    ['==', ['get', 'permit_issued'], true], CATEGORY_BY_KEY.permit_issued.color,
    ['==', ['get', 'plan_check_approved'], true], CATEGORY_BY_KEY.plan_check_approved.color,
    ['==', ['get', 'application_submitted'], true], CATEGORY_BY_KEY.application_submitted.color,
    ['==', ['get', 'cleanup_complete'], true], CATEGORY_BY_KEY.cleanup_complete.color,
    CATEGORY_BY_KEY.none.color,
  ]
}

export const LANE_SIGNAL_INFO: Record<string, { label: string; color: string }> = {
  no_public_evidence: { label: 'No public evidence', color: '#8c8c93' },
  activity_scheduled: { label: 'Activity scheduled', color: '#9aa7d6' },
  activity_attempted: { label: 'Attempted / failed', color: '#c98a3d' },
  in_progress: { label: 'In progress (agency-reported)', color: '#5f9fd0' },
  milestone_reached: { label: 'Milestone reached', color: '#3fa06a' },
  conflicting: { label: 'Conflicting sources', color: '#c05b8f' },
}
