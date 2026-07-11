# Rebuild Score Methodology

Every destroyed lot gets a **rebuild score: 0–100**, rendered on the map as a continuous
red → green gradient. The score is *not* a static status label — it blends the lot's
current pipeline stage with how it is moving relative to its cohort.

## 1. Stage bands

Each parcel's event timeline places it in a stage. Stages map to score *bands*, not
points, so movement-within-stage is visible:

| Stage                              | Band     | Signal                                          |
|------------------------------------|----------|-------------------------------------------------|
| 0 · No activity                    | 0–7      | No debris sign-off, no application on file       |
| 1 · Lot cleared                    | 8–14     | Debris removal complete (USACE/private sign-off) |
| 2 · Plan check                     | 15–39    | Permit application submitted, not yet issued     |
| 3 · Permitted                      | 40–49    | Building permit issued, no inspection activity   |
| 4 · Under construction             | 50–92    | Inspections progressing (see milestones)         |
| 5 · Complete                       | 100      | Certificate of Occupancy / final approval        |

Construction milestones interpolate within band 4 by the furthest inspection milestone
passed: foundation/soils ≈ 55, framing/sheathing ≈ 68, MEP rough ≈ 76,
insulation/drywall ≈ 83, finals in progress ≈ 90.

## 2. Velocity adjustment (within band)

For each stage we compute the **cohort distribution of days-in-stage** across all
destroyed lots. A lot's position within its band shifts by up to ±6 points:

- **Moving** (time-in-stage below cohort median, or recent event < 30 days): drifts to
  the top of its band.
- **Stalled** (time-in-stage > 1.5× cohort median with no recent events): sinks to the
  bottom of its band.

This is what makes "permitted six months ago, silent since" visibly different from
"permitted last week" — same stage, different color.

## 3. Predicted completion

For every observed stage transition (submitted→issued, issued→first inspection, each
inspection milestone→next, finals→CofO) we compute cohort median durations from lots
that have made the transition. A lot's predicted completion is:

```
today + Σ remaining-stage estimates
where current-stage estimate = max(median_stage − days_already_in_stage, p25_stage)
```

This is a deliberately simple conditional-median model (a pragmatic stand-in for
survival analysis); with only ~17 months of history, fancier models would overfit. The
UI presents it as a range ("est. late 2027"), never a date, and labels it an estimate.

## 4. Honesty rules

- A lot with no data is **deep red**, not hidden.
- `summary.json` reconciles our computed counts against the latest official LADBS/County
  published aggregates; the UI links to both. If we drift >5% from official numbers we
  show a data-quality notice rather than silently presenting our number as truth.
- Every parcel card deep-links to the primary record (LADBS permit page) so anyone can
  audit any lot.
