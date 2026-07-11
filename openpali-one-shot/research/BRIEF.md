# Research brief and source map

Prepared 2026-07-11. This is a decision-oriented source map, not preloaded
truth. Public schemas, counts, terms, docs, and model behavior can change. Use
the source-researcher subagent to re-verify any fact that affects code or a
public claim, and preserve the retrieved evidence.

## Load-bearing decisions

1. Use Fable 5 for principal synthesis and implementation, with one deliberate
   `xhigh` session setting. Use read-only subagents for input-heavy archaeology,
   source research, methods review, spatial review, and independent QA.
2. Use Claude Code `/goal` to sustain turns, not to certify the product. Its
   small evaluator sees the transcript and cannot run tools.
3. Keep acceptance criteria outside the builder's control. Fresh evaluator
   evidence and machine gates decide completion.
4. Correct data semantics and publication integrity before ML or new 3D work.
5. Model recovery as parallel milestone lanes. Cleanup is not necessarily a
   prerequisite for application submission, and scheduled activity is not an
   achieved milestone.
6. Treat the existing 0–100 score as an unvalidated communication heuristic.
   Use censoring-aware descriptive baselines before conditional prediction.
7. Keep static-first publication until measured operational complexity earns an
   orchestrator/database. Borrow experiment discipline from Plexe; do not import
   its generic agent/AutoML stack as domain validity.
8. Default to openly licensed/public-domain spatial baselines. Disable
   LARIAC/EagleView derivatives unless rights are affirmatively documented.

## Fable 5 and Claude Code

- [Prompting Claude Fable 5](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5)
  documents long-horizon autonomy, `high`/`xhigh` effort, evidence-grounded
  progress, asynchronous subagents, compact memory, early-stop mitigation, and
  the warning that older over-prescriptive scaffolds can reduce performance.
- [Models overview](https://platform.claude.com/docs/en/about-claude/models/overview)
  identifies `claude-fable-5`, generally available June 9, 2026. Claude Code
  selects it with `--model fable`; it is not the default.
- [Keep Claude working toward a goal](https://code.claude.com/docs/en/goal)
  explains that `/goal` starts another turn after a fresh transcript-only
  evaluator says the condition is unmet. Active goals resume with a session.
- [Custom subagents](https://code.claude.com/docs/en/sub-agents) documents fresh
  contexts, background behavior, worktree isolation, tool restrictions, and
  persistent memory. Subagents cannot spawn subagents.
- [Claude Code plugins](https://code.claude.com/docs/en/plugins) and the
  [plugin reference](https://code.claude.com/docs/en/plugins-reference) support
  task-local agents and hooks without modifying root `.claude/` files.
- [Hooks](https://code.claude.com/docs/en/hooks) support pre-tool guardrails,
  compaction/start context injection, exact evaluator-output capture, and a
  deterministic blocking `Stop` decision. A `/goal` prompt evaluator is not a
  substitute for that machine gate.
- [Sandboxing](https://code.claude.com/docs/en/sandboxing) documents OS-level
  filesystem/network boundaries, `denyWrite`, and `failIfUnavailable`.
  Host-wide bypass permissions are not appropriate for this run.
- [Worktrees](https://code.claude.com/docs/en/worktrees) normally branch from
  `origin/HEAD`; `worktree.baseRef: head` is required to carry the deliberately
  prepared local snapshot. Interactive cleanup can delete the branch and all
  new commits, so the human handoff must choose Keep.
- [Session management](https://code.claude.com/docs/en/sessions) explains named
  interactive resume and the UUID required to resume `-p` sessions.
- [Subprocess environment scrubbing](https://code.claude.com/docs/en/env-vars#claude-code-subprocess-env-scrub)
  keeps Claude/provider authentication in the parent while removing those
  credentials from Bash, hooks, and stdio MCP children.

Local Claude Code was 2.1.207, newer than Fable's 2.1.170 minimum. This harness
pins 2.1.207 as its tested floor because it relies on newer headless hook and
worktree behavior. No active Claude Code login was present during preparation;
account entitlement was not tested. Anthropic currently says Fable is unavailable for
zero-data-retention use and uses 30-day retention; this run must contain only
public project data. Capture fallback notices so a run that falls back to Opus
4.8 is not mislabeled as pure Fable.

## Long-horizon agent evidence

- [Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
  supports initializer/orientation artifacts, incremental progress, Git state,
  feature contracts, and clean handoffs across contexts.
- [Harness design for long-running application development](https://www.anthropic.com/engineering/harness-design-long-running-apps)
  found fresh evaluator/browser use and concrete contracts valuable, while
  later removing scaffold layers that stronger models no longer needed.
- [Building a C compiler with parallel Claudes](https://www.anthropic.com/engineering/building-c-compiler)
  demonstrates isolation, concise deterministic feedback, reference oracles,
  Git handoffs, and specialist sweeps; it also cost about $20,000 across roughly
  2,000 sessions and remained an experiment.
- [SWE-agent's agent-computer interface paper](https://arxiv.org/abs/2405.15793)
  treats tool/interface design as part of coding-agent performance.
- [SWE-Marathon](https://arxiv.org/abs/2606.07682),
  [SWE-EVO](https://arxiv.org/abs/2512.18470), and
  [RoadmapBench](https://arxiv.org/abs/2605.15846) report that long, multi-file
  software evolution remains difficult; self-verification, premature stopping,
  and partial progress are common failure modes.
- [FrontierSWE](https://www.proximal.ai/blog/frontierswe) uses long budgets and
  partial scoring. A leading rank is evidence of relative progress, not proof
  that a one-shot system is production-ready.

These sources argue for one ambitious case study with complete trace/evidence,
not calling one successful-looking run a benchmark.

## Existing authoritative civic sources

### Current P0 sources

- [LA County parcels/debris layer](https://services.arcgis.com/RmCCgQtiZLDCtblq/arcgis/rest/services/Parcels_Debris_Removal_Public/FeatureServer/0)
  defines the current parcel universe and contains jurisdiction, damage,
  cleanup, and rebuild-progress fields. Snapshot the exact layer metadata at
  `/0?f=pjson`; service summaries and search indexes can be stale.
- [LADBS Palisades permit layer](https://services5.arcgis.com/7nsPwEMP38bSkCjy/arcgis/rest/services/LADBS_WF_Fire_Data_Palisades_Recovery_Area/FeatureServer/0)
  contains submit, corrections, approval, issue, CofO, permit type/status, and
  `PALISADES_WF_REBUILD`. Define qualifying primary-rebuild semantics instead
  of ignoring that field.
- [LADBS wildfire inspection service](https://services5.arcgis.com/7nsPwEMP38bSkCjy/ArcGIS/rest/services/LADBS_WF_Inspection_Data_tbl_Palisades_Recovery_Area/FeatureServer)
  contains inspection request/status/description. Preserve the agency outcome
  taxonomy; descriptions and scheduled dates are not achieved milestones.
- [LA Strong recovery dashboard](https://recovery.lacity.gov/) says its LADBS
  metrics update hourly and is useful for independently specified definitions
  and reconciliation.
- [LA County permitting dashboard](https://recovery.lacounty.gov/rebuilding/permitting-progress-dashboard/)
  covers County recovery and must not be mixed silently with City-of-LA event
  semantics.
- [LA County debris guidance](https://recovery.lacounty.gov/road/debris-removal/)
  distinguishes government cleanup from private opt-out; opt-out is not proof
  of final clearance.
- [LA City open-data terms](https://data.lacity.org/terms-of-use) warn that data
  may be corrected/overwritten and prior versions may not be retained. This
  makes OpenPali's immutable raw snapshots load-bearing.

### Candidate cross-checks and later additions

- [LA City permit applications](https://data.lacity.org/d/gwh9-jnip) and
  [Certificates of Occupancy](https://data.lacity.org/d/3f9m-afei) can provide
  public deep links and cross-checks, with their own cadence and schema.
- [CAL FIRE Palisades incident/DINS](https://www.fire.ca.gov/incidents/2025/1/7/palisades-fire)
  is a structure damage source. DINS structure counts cannot be compared
  directly with parcel counts.
- [Malibu rebuild dashboard](https://maliburebuilds.org/rebuild-dashboard/)
  is a coarse official view. The repo's internal marker endpoint is not a
  documented public contract; snapshot it and seek permission or replace it.
- [California DOI wildfire claims tracker](https://www.insurance.ca.gov/01-consumers/180-climate-change/Wildfire-Claims-Tracker.cfm),
  [OpenFEMA IHP](https://www.fema.gov/api/open/v2/RegistrationIntakeIndividualsHouseholdPrograms),
  and [SBA disaster loans](https://web.data.sba.gov/en/dataset/disaster-loan-data)
  are aggregate context, not parcel-level truth or resident predictors.

Do not add sources merely to increase row count. Each source needs a user claim
it enables, stable access, exact terms, a quality contract, a join model,
freshness behavior, and an explicit unknown/conflict path.

## Statistical and ML constraints

The observation process is censored and source-lagged. Parcels that have not
advanced are right-censored, unknown milestone dates may be interval-censored,
and withdrawals/expiry/alternative outcomes can compete. Current/latest LADBS
status, `DAYS_TO_PC_APPROVED`, `DAYS_TO_PERMIT_ISSUE`, and later milestone dates
are outcomes and leak the future if used in historical feature rows.

Start with permit/application-level descriptive multi-state analytics:

- [NIST on censoring](https://www.itl.nist.gov/div898/handbook/apr/section1/apr131.htm)
  and [Kaplan-Meier](https://www.itl.nist.gov/div898/handbook/apr/section2/apr215.htm)
  provide baseline concepts.
- [Putter, Fiocco, and Geskus on competing risks and multi-state models](https://onlinelibrary.wiley.com/doi/10.1002/sim.2712)
  covers intermediate states, competing transitions, state probabilities, and
  data preparation.
- [Consistent Brier-score estimation under right censoring](https://pubmed.ncbi.nlm.nih.gov/17240660/)
  and the [scikit-survival evaluation guide](https://scikit-survival.readthedocs.io/en/stable/user_guide/evaluating-survival-models.html)
  support time-dependent discrimination, Brier score, and censoring-aware
  evaluation.
- [NIST AI RMF](https://www.nist.gov/itl/ai-risk-management-framework) is a
  useful risk/governance frame for consequential public predictions.

Use rolling-origin temporal evaluation and keep the final evaluation untouched.
Publish risk sets, sample sizes, uncertainty/coverage, cohort errors, and
“median not estimable” when appropriate. Do not force overall home-completion
prediction from approximately 17 observed completions and corrupted stage-4
labels.

Policy analysis is not MVP prediction. It needs an intervention estimand,
exposure/eligibility dates, a defensible comparison, pre-trend and contamination
analysis. [Callaway and Sant'Anna](https://doi.org/10.1016/j.jeconom.2020.12.001)
is one reference for staggered difference-in-differences. A City-versus-Malibu
before/after chart is not causal evidence.

## Experimentation and orchestration

- [Plexe](https://github.com/plexe-ai/plexe) is an Apache-2.0 generic tabular
  model-building system with a multi-agent experiment workflow. Useful patterns
  are hypothesis records, metric selection, robustness checks, self-contained
  model artifacts, and experiment tracking. Its agents do not guarantee valid
  censoring, temporal leakage control, or causal inference.
- [Prefect tasks/flows](https://docs.prefect.io/v3/concepts/tasks) can add
  retries, caching, concurrency, state, and observable deployments. The current
  one-process pipeline should first gain idempotency, manifests, atomic publish,
  and failure tests. Adopt Prefect only if measured operations justify it.
- [MLflow tracking](https://mlflow.org/docs/latest/ml/tracking) becomes useful
  when more than one valid model/experiment actually exists. A local versioned
  experiment folder is sufficient for the first baseline.
- [GitHub Actions schedule behavior](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)
  may be delayed or dropped under load. Schedule off-hour, provide manual
  dispatch, and monitor freshness independently.

## Open and conditional spatial sources

Safe first baselines:

- [USGS 2025 post-wildfire LiDAR](https://www.usgs.gov/3d-elevation-program/science/2025-post-wildfire-lidar-data-los-angeles-ca)
  provides public-domain 0.5 m DEM/DSM for the Palisades, acquired 2025-01-21,
  NAD83(2011)/UTM 11N with NAVD88 Geoid18 meters. USGS calls it as-is and not
  reviewed for accuracy; it is a historical emergency baseline, not survey or
  current-rebuild evidence.
- [NOAA 2025 emergency imagery](https://storms.ngs.noaa.gov/storms/2025_eri/index.html)
  and its [metadata](https://www.fisheries.noaa.gov/inport/item/74399) provide
  open January 28 imagery with planning/informational accuracy caveats. The
  Maxar imagery in the same viewer has separate CC BY-NC 4.0 terms.
- [NAIP](https://www.usgs.gov/centers/eros/science/usgs-eros-archive-aerial-photography-national-agriculture-imagery-program-naip)
  is a public-domain pre-fire regional baseline, not frequent house-stage
  monitoring.

Conditional/commercial options such as 50 cm SkySat may detect large exterior
changes, not permits, interiors, or inspection outcomes. Drone acquisition
requires a consent/operations program plus current FAA Part 107, Remote ID,
airspace, VLOS, people/vehicle, and NOTAM/TFR compliance; it is not a software
feature in this one-shot.

## LARIAC/EagleView rights blocker

The repo hotlinks Pictometry imagery and distributes derived LARIAC 3D assets.
Primary evidence indicates restrictions:

- [LA County 2023 aerial imagery item](https://www.arcgis.com/home/item.html?id=b301429f8bc1469bb2bbd5a6c3330abe)
  calls it EagleView licensed content shared with LARIAC members.
- [Countywide building outlines item](https://arcgis.gis.lacounty.gov/arcgis/rest/services/DRP/GISNET_Public/MapServer/434/iteminfo)
  says “LARIAC Members only.”
- [January 2025 Palisades imagery item](https://www.arcgis.com/home/item.html?id=fd079906f14b44efac6f11b6f0c4644f)
  says “For County and LARIAC use only.”
- [LARIAC4-7 authorized-user NDA](https://egis7.gis.lacounty.gov/hub/lariac_documents/LARIAC4-7_NDA_20230321.pdf)
  describes proprietary/confidential EagleView products, restricted internal
  noncommercial project use, and limits on dissemination.
- [LA County GIS terms](https://egis-lacounty.hub.arcgis.com/pages/terms-of-use)
  add informational-only and access restrictions.

Written current-cycle rights must cover display/hotlinking, caching,
derivatives, redistribution, and training. If they do not, disable those assets
and use open alternatives. Do not infer permission from endpoint reachability.

[Esri's Wayback metadata guidance](https://www.esri.com/arcgis-blog/products/arcgis-living-atlas/imagery/wayback-with-world-imagery-metadata)
states that release dates are publication dates, not acquisition dates. Verify
location/zoom-specific capture/provider metadata or label only the release.

## 3D and renderer boundary

The current content is pre-fire LARIAC-derived mesh/surfels packed into a custom
`.splat` format and tinted by an invalid civic score. It is not a learned current
3DGS. Correct the label and license boundary first.

- [OGC 3D Tiles 1.1](https://docs.ogc.org/cs/22-025r4/22-025r4.html) uses glTF
  as primary content. The custom extension is project-specific, not generally
  interoperable 3D Tiles compliance.
- Khronos announced a [release candidate for `KHR_gaussian_splatting`](https://www.khronos.org/news/press/gltf-gaussian-splatting-press-release)
  in February 2026. Keep a format boundary rather than rewriting during MVP.
- [gsplat](https://www.jmlr.org/papers/v26/24-1476.html) is Apache-2.0 and a
  better later research candidate than code with research-only licensing.

For this run: 2D first; lazy 3D; one acquisition epoch and snapshot; explicit
CRS/vertical datum and coverage; reference scenes; cold/warm transfer, CPU,
frame-time, actual allocation, overdraw where available, context loss, and
visual comparisons. Distinguish transparency ordering, coplanar z-fighting,
and registration/datum errors. Do not rewrite to WebGPU.
