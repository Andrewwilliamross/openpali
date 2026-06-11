# Direction & Roadmap — June 2026

**Owner:** Fable 5, acting CTO, RE\SPRING · **Date:** 2026-06-11
**Status:** authoritative. Responds to and supersedes the roadmap section of the
2026-06-11 research audit (external document, prepared by Andrew Ross, Codex
GPT-5.5 xHigh, and Gemini 3.5 Thinking). Audit items 6–7 were redacted in the
copy I received; nothing here depends on them.

**Mission order:** (1) improve quality of life for the people of Pacific
Palisades; (2) demonstrate that an applied-AI lab can build advanced technology
for public benefit. Goal 2 is earned only by shipping goal 1 with rigor. Any
feature that would impress a lab audience but could mislead a resident is cut.

---

## 0. The call

openpali stops being primarily a *status tracker* and becomes **evidence
infrastructure for the rebuild**: every number auditable to a primary record,
every one of the 5,877 lots visible and honestly labeled in 2D and 3D, and — the
new center of gravity — **resident-facing evidence products** aimed at the
fights that actually gate rebuilds in mid-2026: insurance settlements, financing
gaps, and the decision to start.

Three verified facts force this reweighting:

1. **The bottleneck moved.** Debris is done (5,590/5,877 cleared). City
   permitting now runs ~3× pre-fire speed and is widely described as improved.
   The #1 and #2 blockers in every 2026 survey and resident account are
   **insurance payouts and out-of-pocket money** — 70% of Palisades victims
   under- or uninsured, ~$1.5M average payout shortfall, 38% exhausting ALE,
   median fire debt >$100K, 4-in-10 households borrowing. Only 2,045 of 5,877
   lots (35%) have even entered the permit pipeline; the modal household is not
   building yet, and "fear of being first" plus money is why.
2. **Status maps are now table stakes.** Since this project started, LA County
   shipped a parcel-level color-coded dashboard (12,000+ projects, daily
   refresh) and residents built **PaliBuilds.com** (SFD permit tracking, lot
   sales, CoO counts, DWP meter-delay tracking, contractor directory). A
   prettier permit map is no longer a contribution. Our unique assets are the
   **full-footprint cross-jurisdiction APN spine, open auditable artifacts, the
   3D layer, and AI engineering depth** — so we go where those compound.
3. **Trust is the scarce asset.** In May 2026 Google Maps silently reverted the
   Palisades to pre-fire imagery for days; even Google mislabels time. Our
   differentiation is provenance: capture dates, source hashes, coverage labels,
   reconciliation against official numbers, and a public correction path.

Positioning: **complement, don't compete.** PaliBuilds owns community trust for
City-SFD permit stats; the County owns the official dashboard. We are the open,
full-footprint (City + County + Malibu), provenance-grade data layer and 3D twin
that others can build on — and the evidence compiler nobody else is building.

---

## 1. Repo ground truth (verified 2026-06-11)

Audit numbers all reconcile against live artifacts:

| Claim | Verified |
|---|---|
| 5,877 destroyed parcels (`summary.json`) | ✓ |
| 4,596 LADBS rows (`meta.json`) | ✓ |
| 10,016,113 splats / 326,829,952 bytes (`manifest.json`) | ✓ (tiles dir measures 318 MB on disk) |
| 4,976 parcels in `picking.json` | ✓ |
| 717 `static_baseline` (`data/spatial/meta.json`, generated) | ✓ — plus 184 `priors_footprint_fallback`; 4,976+184+717 = 5,877 exactly |

Code-claim verdicts (file-precise):

- **Cold-start gap confirmed:** `extract_footprint_prior` emits
  `kind="mesh_vertices"` (`pipeline/core/spatial/scene_client.py:376`) while
  `export_web_tiles` reads only `kind="splats"`
  (`pipeline/core/spatial/web_export.py:106`). Intentional staging, but the
  resident-facing effect stands: **901 lots have no 3D presence** (184 fallback
  + 717 baseline). The fix is cheap — `surfels.py` already has the
  point→splat machinery.
- **Scoring** (`pipeline/palisades/score.py:47–163`): cohort conditional
  medians, deterministic, humanized ranges; coarse (Malibu/county) parcels
  correctly quarantined from cohort stats. As METHODOLOGY.md says, honest for
  v1 — uncertainty work goes to Track R.
- **Texture race downgraded:** generation guards + hysteresis exist; worst case
  is a one-frame placeholder with graceful null fallback. Two-phase commit is
  polish, not a fire.
- **ENU→UV linearization confirmed** (`texturing.ts:150–157`, constants shared
  with the render layer). Quantify drift before "fixing" anything.
- **Confirmed absent:** coverage.json, snapshot_id, observation-state, STAC,
  Parquet civic event tables, correction flow, capture ingestion wiring,
  overdraw/GPU instrumentation. `register_capture()` exists, unwired.
- **Contract violation found (audit missed it):** `summary.json.baselines` is
  an **empty list** even though ARTIFACTS.md and the README promise official
  reconciliation entries. The reconciliation honesty we advertise is not being
  emitted. Fix in PR1.
- Tests: 35 Python confirmed; web is 20 (audit said 17).

---

## 2. External reality, June 2026 (what reweighted the roadmap)

Money, not permits:

- "The number one issue is insurance. They are not paying out, and so homeowners
  are stuck waiting… to even be able to hire an architect" — PaliBuilds'
  Kambiz Kamdar [The Real Deal, 2026-03-18]. Out-of-pocket gap ranks #1 in the
  Department of Angels 5th survivor survey (~May 2026); 71% extremely/very
  worried insurance won't cover costs [NORC/PPCC, Jan 2026].
- FAIR Plan: court ruled its smoke-damage standard illegal (Aliff, Jun 2025);
  CDI enforcement action for systematic denials (Jul 2025); mass tort ongoing.
  State Farm: CDI exam found 398 Unfair Claims Practices Act violations in 114
  of 220 sampled claims (May 2026). **Documented timelines are leverage** —
  exactly what an evidence compiler produces.
- Fee waiver still rests on a revocable emergency order; final ordinance vote
  unscheduled (Jun 2026). Policy regime tracking matters.
- Pipeline state: ~1,134 of our parcels hold issued building permits
  (628 permitted + 489 UC + 17 complete) — consistent with LADBS "1,070+
  permits / 540+ addresses" and PaliBuilds' 928 City-SFD-only count. Our
  numbers cross-validate; now make that reconciliation visible in-product.
- Return/market: ~25% of residents back; 586 lots sold (+45 in May);
  investors ~40% of recent lot sales; 64% intend to rebuild but only 13% of
  heavily-impacted SF owners had started construction [NORC/PPCC]. Block-level
  momentum display directly targets "fear of being first."
- Utilities emerging as the *completion-side* blocker: LADWP meter installs
  (PaliBuilds began tracking waits Apr 2026); undergrounding 2027–2031 with
  block-level easement decisions.

New data we should use:

- **CC0 post-fire LiDAR exists**: NV5/ALERTCalifornia flew the Palisades
  2025-01-21 (0.5 m DEM/DSM, OpenTopography DOI 10.5069/G9DR2SPG). Public
  post-fire ground truth, no partnership needed.
- **LARIAC7 pre-fire QL1 LiDAR is now fully public** via USGS 3DEP (fall 2025).
- **EPIC-LA Case History layer** now carries 7 fire-rebuild phase fields,
  refreshed daily (geohub item `b2a835d49c194029a525fb60cf24aa59`) — upgrades
  our county-unincorporated parcels from "coarse" to phased status.
- LARIAC8 is flying now (2026–2028), member-locked → county partnership is the
  unlock for current orthos. Google's 3D mesh remains pre-fire.

---

## 3. Decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | **Adopt the audit's trust core, immediately**: source hashes, query params, schema fingerprints, run_id, snapshot_id on every artifact; populate `summary.baselines`; validation gates that fail emit. | The audit is right that provenance is the production gap; and we're already violating our own artifact contract (empty baselines). |
| D2 | **Render all 5,877 parcels in 3D, each labeled by geometry source.** Surfel-sample the 184 footprint extrusions into splats; emit parcel-prism splats for the 717 no-data lots; ship `coverage.json` + UI badges (LARIAC model / footprint extrusion / parcel prism). | A resident whose home is invisible reads it as "my home doesn't count." Honesty labels beat fidelity. |
| D3 | **Kill generative geometry in product. Permanently.** No diffusion priors, no inpainting, no neural completion in anything public. Research-only, never published imagery. | One hallucinated "rebuilt home" screenshot circulating on Nextdoor ends the project's credibility. The audit's own constraint list (#11) prices the safety cost above the feature's value. |
| D4 | **No enterprise data-stack migration.** No Dagster/Iceberg/Great Expectations/OpenLineage adoption. We implement their *contracts* (hashes, lineage fields, expectations, snapshot pinning) inside the existing pipeline + CI — ~200 lines, not four platforms. | Solo-operator + AI-agents team. Trust comes from auditability, not tool brands. Revisit if the team grows. |
| D5 | **Evidence-pack export becomes the flagship resident feature**: per-parcel, citation-grade timeline bundles (official records, dates, deep links, source hashes) exportable for insurance disputes, contractor negotiations, appeals. Built from public records first; no private-document vault until a real consent/security design passes review. | Insurance is the #1 bottleneck and enforcement actions show documentation wins. This is the "evidence compiler" bet from the audit, scoped to ship. |
| D6 | **Deterministic ETAs get demoted, not deleted**: keep the labeled range short-term; add censoring-aware cohort "comparable cases" (with IQR and explicit %-still-pending) at 60 days; survival model replaces the ETA presentation by day 90; suppress any cohort below n=15 (reuse score.py's MIN_SAMPLE). | Audit §8–9 is correct; 65% of lots haven't started, so censoring isn't a detail — it's most of the distribution. |
| D7 | **Add observation-state per APN**: `publicly_observed / jurisdiction_coarse / source_lagged / ownership_changed / resident_verified / private_opaque / unknown`. Ingest EPIC-LA rebuild phases (county) and assessor transfers (ownership churn — neutral label only, investor analytics aggregate-only). | Absence of evidence ≠ inactivity; 586 sold lots are a different civic story than 586 stalled ones. Fairness guardrail on investor labeling. |
| D8 | **Partner, don't compete**: approach PaliBuilds/Palisadian-Post for data cross-validation and feature complementarity; PPCC + Department of Angels for resident validation; County eGIS re LARIAC access. Stand up a 5–10 household resident council before building resident-facing UX. | They have trust and distribution; we have engineering depth and footprint coverage. Duplicating a fire survivor's volunteer project would be both wasteful and bad citizenship. |
| D9 | **Capture program: collect first, reconstruct later.** Ship consent-first photo/video collection with an observability gate (prior availability, parallax, GPS dispersion) per audit §1; registration/3DGS training stays in the research track behind human QA; nothing crowdsourced renders publicly without passing it. | `register_capture()` is built but the hard part is consent UX + quality gating, not ICP. Don't let a research problem block the civic track. |
| D10 | **3D performance is productized, not assumed**: code-split so 3D loads on demand; ship renderer instrumentation (draw stats, overdraw heat mode, GPU timers where available); set device budgets before adding any new 3D features. | Audit §4 is right that fill-rate is unproven; and displaced residents on old devices are the actual audience. |
| D11 | **Geometry fixes are trigger-gated**: per-node affine UV only if measured drift > 0.5 texel (write the test first); two-phase texture commit only if instrumentation shows visible pops. | Verified code review shows current guards degrade gracefully. Measure, then fix. |
| D12 | **Defer**: STAC catalog (until multi-acquisition imagery exists — do GeoParquet bbox + snapshot manifest now), semantic/open-vocab splats, satellite tasking budget (Sentinel-2 free + public orthos first), plan-to-geometry parsing (accept uploads, store, don't parse yet), contractor *risk scores* (publish neutral public facts only — license status, permit velocity — pending counsel review of anything evaluative). | Sequencing. Each has a revisit trigger in §9. |
| D13 | **Post-fire truth surface**: ingest the CC0 Jan-2025 LiDAR as terrain/clearing ground truth and DEM-differencing baseline; use LARIAC7 public QL1 as the pre-fire elevation baseline. | Free, public-domain, and turns "4D" from a splat-research aspiration into a shippable change product. |
| D14 | **One public research artifact per quarter**, starting with a policy-impact note (e.g., EO6 self-certification effect on issuance times, measured from our event data — uptake numbers are unpublished anywhere). | Serves goal 2 honestly: civic research with methods, not demos. |

---

## 4. Roadmap

### Track A — Trust Core (every number auditable)

| Deliverable | Acceptance bar |
|---|---|
| Provenance fields per source: `sha256`, query params, schema fingerprint, row count, `run_id` | Present in `meta.json` for 100% of sources; stable across `--offline` reruns |
| `snapshot_id` stamped across parcels.geojson / details.json / summary.json / meta.json / tiles manifest / picking.json | Frontend asserts matching snapshot or shows stale labels |
| `summary.baselines` populated from the validate stage (LADBS oracle; County dashboard; Malibu) | Non-empty every run; UI shows ours-vs-official with drift % (>5% triggers the notice METHODOLOGY.md already promises) |
| Expectation gates in-pipeline: APN parse rate, dup APNs, row-count deltas, taxonomy drift, join-rate floor | Violations fail emit (artifacts unchanged) and write an incident note into meta.json |
| EPIC-LA rebuild-phase ingestion for county parcels; assessor-transfer ingestion → `ownership_changed` | County parcels show phased status; observation-state field live in details.json |
| Resident correction flow ("report a problem with this lot") | Static-site compatible (GitHub-issue backed), triage SLA ≤ 7 days, `resident_verified` state renders |

### Track B — Resident Leverage (move money and decisions)

| Deliverable | Acceptance bar |
|---|---|
| Parcel Truth Card v2: status + provenance + coverage + next-step guidance | Every field traceable to a source link; no unlabeled model output |
| Evidence pack v0: exportable per-parcel PDF/JSON timeline citing official records | A resident can hand it to an adjuster/contractor; every line carries source + retrieval date + hash |
| Comparable-cases view: censoring-aware cohort stats (medians, IQR, % still pending), suppressed below n=15 | Replaces bare ETA emphasis; survives backtest on withheld months |
| Block momentum view ("5 of 14 lots on your block are active") | Anti-shaming review passed: no slowness rankings, no individual blame framing |
| Permit navigator v0: eligibility paths (EO1/EO8/self-cert/standard plans) with citations to current rules | Every claim cites the official bulletin; flagged "assistance, not advice" |

### Track C — Spatial Truth (3D that tells the truth)

| Deliverable | Acceptance bar |
|---|---|
| 100% parcel renderability: surfel-ize the 184 footprint priors; prism splats for the 717 baseline lots | `manifest.parcels == 5877`; picking covers all APNs |
| `coverage.json` + UI geometry-source badges + imagery vintage labels everywhere | No 3D pixel without a source label; ground imagery shows capture date (LARIAC7 ortho: Oct 2025) |
| Code-split: 3D renderer + texturing load only on 3D entry | Initial JS payload measurably reduced (target: core bundle < ⅓ of current) |
| Renderer instrumentation: draw-list size, resident bytes, sort time, texture lifecycle counters, overdraw heatmap, GPU timing where available | Debug HUD behind a flag; p50/p95 fragments-per-pixel measurable on real devices |
| UV drift test (exact Mercator vs linearized corners across all nodes) | Drift report in CI; affine fix applied only where > 0.5 texel (D11) |
| Post-fire LiDAR ingestion (CC0, Jan 2025) as terrain truth + DEM differencing baseline | Pre/post elevation diff product per parcel; grading/clearing visible |

### Track R — Research (lab bets, explicitly second priority)

1. **Survival modeling with censoring** (lifelines-class, jurisdiction/coastal/
   slope covariates, backtested on withheld history) → feeds Track B comparable
   cases; never renders a parcel-level date without uncertainty.
2. **Imagery change detection** (Sentinel-2 free cadence + public orthos +
   LARIAC8 when accessible) → per-parcel "site changed" signals cross-checking
   civic events; the pragmatic 4D before any splat training.
3. **Capture pilot** with 1–2 volunteer block captains: consent UX,
   observability gate, registration QA loop (`register_capture` finally wired,
   offline, human-reviewed).
4. **Policy impact note #1**: EO6 self-certification effect on issuance times
   (D14).

### 30 / 60 / 90 rollup

- **Day 30:** Track A provenance + snapshot_id + baselines + gates live; D2
  render-all-parcels shipped with coverage.json + badges; code-split done;
  EPIC-LA ingestion. *(PR1–PR3 below.)*
- **Day 60:** observation states + correction flow + comparable-cases v1 +
  evidence pack v0 + block momentum; renderer instrumentation + drift report;
  post-fire LiDAR ingested; PaliBuilds/PPCC conversations held; resident
  council seated.
- **Day 90:** survival model backtested and presented as comparable-cases;
  capture pilot designed with consent review; change-detection prototype
  running; policy note #1 published; public METHODS/provenance page live.

---

## 5. First three PRs (file-precise)

1. **Provenance & reconciliation** — `pipeline/palisades/sources.py` (capture
   raw-response sha256 + query params at fetch), `validate.py` (emit baseline
   comparisons it already computes), `emit.py` (write `run_id`, `snapshot_id`,
   per-source provenance into meta.json; stamp snapshot_id in all four
   artifacts + tiles manifest). Fixes the empty-`baselines` contract violation.
2. **Render every lot + coverage.json** — `pipeline/core/spatial/runner.py`
   (route footprint priors through `surfels` point→splat sampling, capped
   per-parcel; generate prism splats from parcel polygons + default height for
   static_baseline), `web_export.py` (drop the silent `kind=="splats"` filter
   asymmetry; emit `coverage.json`: APN → civic status, geometry source,
   n_splats, acquisition date, missing reason), `web/src/components/spatial/ParcelDetailCard.tsx`
   (geometry-source badge).
3. **3D on demand** — dynamic `import()` of `web/src/components/spatial/*` from
   `MapView.tsx`; verify bundle split in build output; add the debug-HUD flag
   scaffold for instrumentation.

---

## 6. KPIs

- **Trust:** 100% artifacts carry snapshot_id + provenance; reconciliation
  drift vs official shown in-product; corrections median response < 7 days;
  zero unexplained number changes between runs.
- **Coverage:** 5,877/5,877 parcels rendered + labeled; county parcels phased
  (not coarse); coverage.json consumed by UI.
- **Resident value:** evidence packs generated; corrections submitted/resolved;
  truth-card usage; at least one partner (PaliBuilds/PPCC/DoA) actively
  reviewing or consuming our data.
- **Performance:** 3D out of the core bundle; 0 renders at idle (already
  achieved — keep it); fragments-per-pixel budget established per device tier.
- **Honesty:** no unlabeled geometry, imagery, or model estimate anywhere.

---

## 7. Governance & red lines

- Public METHODS page: scoring, censoring handling, reconciliation, coverage
  semantics, correction SLA. Every model output labeled estimate; every
  generated artifact non-evidentiary (and per D3, none published).
- No parcel-level ETA below cohort n=15; no neighborhood "slowness" rankings;
  investor-ownership analytics aggregate-only.
- Private/resident data only with consent, encryption, revocation, and scoped
  access — and not before a real security design review. Until then the
  evidence pack uses public records only.
- Anything evaluative about named contractors goes through counsel review
  first; neutral public facts only until then.
- Legal/insurance/tax outputs are assistance, not advice; route complex cases
  to licensed professionals.

---

## 8. Explicit kills & defers

| Item | Status | Trigger to revisit |
|---|---|---|
| Generative inpainting / 3D diffusion in product | **Killed** (D3) | None. Research-only, unpublished. |
| Monolithic city-scale 3DGS training | **Killed** | Never — parcel-local submaps only (matches audit's own bet). |
| Dagster / Iceberg / GX / OpenLineage stack | **Rejected** (D4) | Team grows beyond solo + agents, or >3 operators need shared orchestration. |
| STAC catalog | Deferred | We host ≥2 acquisition types beyond LARIAC tiles (captures, LiDAR products). |
| Semantic / open-vocab splats | Deferred | Resident-facing query need that event data can't answer. |
| Commercial satellite tasking | Deferred | Funded budget + a use change detection can't cover free. |
| Plan-to-geometry parsing | Deferred (accept + store uploads only) | Volume of resident/contractor plan uploads justifies the parser. |
| Contractor risk *scores* | Deferred | Counsel review passed. |
| Two-phase texture commit; per-node affine UV | Backlog | Instrumented pops; drift > 0.5 texel (D11). |
| Xactimate/interior reconstruction | Deferred | Consent vault designed + partner (insurance-side) engaged. |

---

## 9. Revisit triggers

Re-open this roadmap when any of: fee-waiver ordinance passes or the emergency
order lapses; FAIR Plan surcharge trial (set 2026-06-30) or smoke-standard
legislation (~mid-2027) resolves; LARIAC8 derivatives release or county grants
access; LADBS/EPIC-LA schema changes break joins; the SB 782 Disaster Recovery
District forms (resolution deadline 2027-01-07); PaliBuilds partnership lands
(merge/divide scope accordingly); or the capture pilot produces its first
QA-passed reconstruction.
