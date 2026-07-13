# Research Memo: Synthetic Spatial Data & Expanding OpenPali's Data Engine

**Prepared for:** OpenPali team
**Date:** 2026-06-27
**Subject:** Concrete avenues to increase data **collection**, **processing**, and **generation** so OpenPali becomes the single most robust data source for the Pacific Palisades.
**Method:** Multi-agent deep-research run (108 agents, 26 primary/secondary sources fetched, 121 candidate claims, 25 adversarially verified by 3-vote panels; 24 confirmed, 1 refuted). Plus a direct technical read of the `lingbot-map` reference repo.

> **How to read this memo.** Per `Docs/Research/README.md`, claims are tagged by evidentiary status:
> - **[VERIFIED]** — survived 3-vote adversarial verification against a primary source (high confidence).
> - **[NAMED LEAD]** — surfaced by search with a real, citable source, but *not* independently verified in this run. Treat as a strong pointer to validate, not a settled fact.
> - **[ASSESSMENT]** — our interpretation/recommendation, not a sourced fact.
>
> Two of the five angles (synthetic-spatial state-of-the-art; authoritative LA data sources) are deeply verified. Three angles (field acquisition, CV detection toolchain, platform/business) returned strong named leads but thinner verification — flagged throughout and consolidated in **§7 Open Questions**.

---

## 1. Executive Summary

1. **"Synthetic Spatial Data" is a real, fast-maturing discipline — and the single most strategically important capability OpenPali can own.** The peer-reviewed literature confirms AI can (a) *generate* satellite/aerial imagery conditioned on geo-metadata, including reconstructing **fire**-damaged structures; (b) *reconstruct* dense 3D/elevation models from ordinary imagery ~300× faster than a year ago; (c) *synthesize* LiDAR point clouds; and (d) *impute* sparse ground-truth via ML interpolation. **But every credible source carries the same warning: synthetic geospatial data diverges from ground truth and must be validation-gated before publication.** This is our moat *and* our liability — see §2.

2. **The `lingbot-map` repo is exactly the right north star for OpenPali's "drive-and-capture" pipeline.** It is not a map app — it is a feed-forward **3D foundation model** that turns *streaming video* into dense 3D geometry (point clouds, depth, camera trajectories) in real time. This is the literal engine for "car drives with a camera → structured spatial output," generalized from one object class (potholes) to the entire reconstructed neighborhood. See §2.4.

3. **A large amount of authoritative, Palisades-specific, free, API-ready data already exists and is under-exploited.** The highest-value target is **CAL FIRE's DINS 2025 Palisades layer** (12,081 per-structure damage assessments, 6,845 Destroyed) served as a public ArcGIS REST FeatureServer. Combined with the LA County Assessor parcel base (2.43M parcels), free post-fire USGS 3DEP LiDAR (16 pts/m²), and FEMA flood layers, OpenPali can stand up a defensible "collect & link" foundation in weeks, not months. See §3.

4. **A critical jurisdictional gotcha:** the Palisades is **City of LA**, not unincorporated county. LA County's EPIC-LA permit API **does not cover the Palisades** — rebuild permits flow through **LADBS**. Any permit-ingestion design that points at EPIC-LA will silently miss the entire neighborhood. See §3.4.

5. **Strategically, do not try to "own the base map."** The 2026 industry consensus (Overture) is that building a proprietary base map is a value trap; the durable moat for a hyperlocal player is **freshness, depth, and linkage** on one geography — exactly what a single-neighborhood focus enables. See §6.

---

## 2. Angle 1 — Synthetic Spatial Data: State of the Art

### 2.1 Definition and the central caveat

**[VERIFIED]** "Synthetic spatial data" is an established, peer-reviewed practice — but AI-derived geospatial data *reproduces some spatial structure while exhibiting critical spatial dissimilarities* from ground truth. The canonical study ("Synthetic geospatial data and fake geography," *Patterns/ScienceDirect* 2024) applied the Mostly.AI platform to Airbnb listings in Florence and documented exactly these "similarities and dissimilarities."
→ Source: https://www.sciencedirect.com/science/article/pii/S2666378324000308
> **Implication:** Any synthetic or imputed layer OpenPali publishes needs an explicit **spatial-similarity validation step** (hold-out ground truth + spatial autocorrelation / distributional checks) before it goes live. Bake this into the pipeline as a gate, not an afterthought.

### 2.2 Generative models for imagery (incl. fire-damage reconstruction)

**[VERIFIED]** **DiffusionSat** (ICLR 2024) is a latent-diffusion foundation model (initialized from Stable Diffusion 2.1) that generates high-resolution satellite imagery conditioned on numerical metadata (lat, lon, timestamp, GSD, cloud cover) plus text. It claims SOTA on **super-resolution, temporal generation, and in-painting**, and demonstrates reconstruction of *"damaged roads and houses for floods, wind, fire, and earthquakes"* (trained/evaluated on xBD/xView-2).
→ Source: https://arxiv.org/html/2312.03606v2
> **Relevance:** This is directly a wildfire-rebuild tool — temporal in-painting can synthesize "what changed" or fill cloud/coverage gaps in the Palisades imagery timeline. **Caveat:** the disaster-reconstruction results are largely *qualitative*, not benchmarked — validate before treating any reconstruction as evidentiary.

### 2.3 3D reconstruction: Gaussian Splatting has crossed the cost threshold

**[VERIFIED]** **EOGS** (Earth-Observation Gaussian Splatting, CVPR 2025) is the first 3D Gaussian Splatting method for digital surface/elevation modeling from multi-date satellite imagery. It matches the prior NeRF SOTA (EO-NeRF) on accuracy while being **~300× faster** — ~3 minutes/scene vs ~15 hours — with elevation MAE within ~0.1 m of NeRF (and slightly *beating* it on structures).
→ Sources: https://openaccess.thecvf.com/content/CVPR2025/papers/Aira_Gaussian_Splatting_for_Efficient_Satellite_Image_Photogrammetry_CVPR_2025_paper.pdf ; https://arxiv.org/html/2412.13047v2
> **Implication:** Generating per-scene 3D/DSM layers for the Palisades is now cheap enough to run routinely (e.g., monthly rebuild-progress 3D snapshots), not a one-off research project.

**[VERIFIED]** **Synthetic LiDAR** is feasible: a denoising diffusion model (DDPM) with novel noise scheduling generates high-quality LiDAR point clouds from image-based (BEV/equirectangular) projections (Sept 2025; part of an established line incl. LiDARGen).
→ Source: https://arxiv.org/abs/2509.18917 — **Caveat:** non-peer-reviewed preprint; "high quality" is author self-assessment. Prefer the *real* USGS 3DEP LiDAR (§3.5) as ground truth and use synthetic LiDAR only to densify/fill.

### 2.4 The `lingbot-map` repo — what it actually is (direct technical read)

**[ASSESSMENT, from direct repo inspection]** `lingbot-map` is **not** a mapping application — it is a **feed-forward 3D foundation model for real-time scene reconstruction from streaming video**. Key technical facts from the repo:

- **Core:** a "Geometric Context Transformer" built on **VGGT** + **DINOv2** vision features (PyTorch 2.8 / CUDA 12.8), unifying coordinate grounding, dense geometric cues, and long-range drift correction (anchor context, pose-reference windows, trajectory memory).
- **Performance:** stable inference at **~20 FPS at 518×378** over sequences exceeding **10,000 frames**; windowed inference for sequences beyond training range.
- **Outputs:** point clouds, depth predictions, camera trajectories, browser-based 3D viewer (Viser), offline flythrough rendering; sky masking for outdoor scenes (ONNX); Open3D / NVIDIA Kaolin for visualization/rendering.

> **Why this is the right reference for OpenPali:** It is the literal engine behind the "car drives with a camera → structured spatial output" thesis, but generalized. Instead of detecting *one* class (potholes), it reconstructs the **full dense 3D geometry** of whatever the camera sees. The OpenPali pattern becomes: **drive/walk the Palisades → lingbot-style model produces a live 3D reconstruction → run detection/segmentation (§5) on the geometry+imagery → emit georeferenced structured records.** This unifies acquisition (Angle 3) and generation (Angle 4) into one pipeline.
> **Caveat:** the deep-research verification pass did *not* independently confirm the repo's performance claims — they are from the repo's own README. Validate with a small Palisades test drive before betting the roadmap on the FPS/quality numbers.

### 2.5 Kriging vs. ML imputation (filling sparse ground truth)

**[VERIFIED]** **RFSI** (Random Forest Spatial Interpolation, *Remote Sensing* 2020) is a viable ML alternative to kriging: it feeds observations at the *n* nearest locations plus their distances as covariates into a random forest. Benchmarked against kriging/regression-kriging/IDW; open-source (R `meteo` package + author GitHub).
→ Sources: https://www.mdpi.com/2072-4292/12/10/1687 ; https://github.com/AleksandarSekulic/RFSI — **Caveat:** in the paper's own synthetic case study, *kriging was most accurate* — RFSI is an alternative, not a strict win. Use whichever validates better per-layer.

---

## 3. Angle 2 — Authoritative & Open Data Sources (the "Collect & Link" foundation)

This is the most actionable section: every item below is **free, public, and API-ingestible today.**

### 3.1 ★ CAL FIRE DINS 2025 Palisades — the single most Palisades-specific dataset

**[VERIFIED]** Per-structure post-fire damage assessment, published on California's state ArcGIS Open Data portal and served as a **public, anonymously-queryable ArcGIS REST FeatureServer** (point features). **12,081 records**: 6,845 Destroyed (>50%), 4,261 No Damage, 732 Affected (1–9%), 171 Minor (10–25%), 72 Major (26–50%). Capabilities: Query/Extract; GeoJSON/CSV/shapefile export; it is an **updatable view** (counts will change).
→ Sources: https://gis-california.opendata.arcgis.com/datasets/CALFIRE-Forestry::dins-2025-palisades-public-view/about ; FeatureServer: `https://services1.arcgis.com/jUJYIo9tSA7EHvfZ/arcgis/rest/services/DINS_2025_Palisades_Public_View/FeatureServer/0`
> **Action:** Ingest now as the damage-status spine. **Important:** a companion claim enumerating the exact `DAMAGE`/`STRUCTURETYPE` coded values was **REFUTED (0-3 vote)** — do **not** hardcode the field domains; **read them live** from the service's `/0?f=json` field metadata.

### 3.2 ★ LA County Assessor Parcel Base — the structured foundation layer

**[VERIFIED]** Authoritative public ArcGIS REST service (`cache.gis.lacounty.gov`, exposing MapServer/FeatureServer/WFS), maintained by the Office of the Assessor. **2,431,782 polygon parcels** covering all of LA County incl. the Palisades, each with ~90–95 fields: AIN/APN, full situs address, use code/type, year built, square footage, beds/baths, assessed land+improvement values, legal description, and **parcel centroid `CENTER_LAT`/`CENTER_LON`**.
→ Sources: https://egis-lacounty.hub.arcgis.com/datasets/la-county-parcel-map-service/api ; query endpoint: `https://public.gis.lacounty.gov/public/rest/services/LACounty_Cache/LACounty_Parcel/MapServer/0/query`
> **Action:** Use APN as the **join key** to link every other dataset (DINS, permits, imagery detections) to a canonical parcel. This is your entity-resolution backbone.

### 3.3 City of LA — two distinct platforms to ingest

**[VERIFIED]** The City runs **two separate** data platforms:
- **GeoHub** (`geohub.lacity.org`) — ArcGIS Hub "location-as-a-service," aggregating hundreds of datasets from 20+ city agencies, with GeoServices/WMS/WFS APIs.
- **DataLA** (`data.lacity.org`) — the general open-data catalog on the **Socrata** stack (SODA API + CSV/JSON).
→ Sources: https://geohub.lacity.org/ ; https://data.lacity.org/ ; https://dev.socrata.com/foundry/data.lacity.org/
> **Action:** Crawl both catalogs for Palisades-bounded layers; they have *different* contents and *different* APIs (GeoServices vs SODA).

### 3.4 ⚠ Permits — the jurisdictional trap

**[VERIFIED]** LA County's **EPIC-LA Case History** service is a live ArcGIS REST FeatureServer refreshed each business day (~9am) — **but it is scoped to UNINCORPORATED LA County only.** The Palisades is within the **City of LA**, whose rebuild permits are handled by **LADBS**. **EPIC-LA does not contain Palisades permits.**
→ Sources: https://services.arcgis.com/RmCCgQtiZLDCtblq/arcgis/rest/services/EPIC-LA_Case_History_view/FeatureServer ; https://planning.lacity.gov/project-review/palisades-rebuild-recovery
> **Action:** Target **LADBS** (`dbs.lacity.gov`) and `recovery.lacity.gov` for permit ingestion — *not* EPIC-LA. This corrects a likely-wrong assumption in any plan that treats "LA County permits" as one source. (Note: this aligns with the prior EPIC-LA finding already in the team's roadmap memory — but re-confirm the LADBS endpoint/feed format, which this run did not verify.)

### 3.5 ★ USGS 3DEP post-fire LiDAR — already flown, free, unrestricted

**[VERIFIED]** USGS 3DEP acquired high-resolution airborne LiDAR over the **Palisades and Eaton** impact areas right after the Jan 2025 fires (contractor NV5, UC/ALERTCalifornia partnership; collected **Jan 21–22 2025 at 16 pts/m², 0.5 m DEM/DSM**, Riegl VQ-1560II + Applanix IMU). **All 3DEP products are free of charge and without use restrictions** (public domain), via The National Map, ScienceBase, AWS public buckets, OpenTopography, NOAA InPort.
→ Sources: https://www.usgs.gov/3d-elevation-program/science/2025-post-wildfire-lidar-data-los-angeles-ca ; https://nv5.com/news/la-fires-data/
> **Action — major shortcut:** Authoritative post-fire LiDAR **already exists**. OpenPali should *ingest* it rather than fly its own first pass, and reserve drone/mobile LiDAR (Angle 3) for *change detection* against this baseline. **Caveat:** data is provisional/as-is, not yet fully QA'd to 3DEP accuracy spec.

### 3.6 FEMA National Flood Hazard Layer (post-fire debris-flow risk)

**[VERIFIED]** NFHL is programmatically ingestible via a live ArcGIS REST MapServer (`hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer`) exposing ~32 layers (FIRM Panels, Flood Hazard Zones, Base Flood Elevations, Levees, LOMRs/LOMAs); supports Map/Query/Data; returns JSON/geoJSON/PBF (NAD83, wkid 4269), capped 2,000 records/request; also bulk download by county/state and via OGC WMS/WFS.
→ Sources: https://www.fema.gov/flood-maps/national-flood-hazard-layer ; https://msc.fema.gov
> **Relevance:** Post-fire debris-flow/flood risk is a documented Palisades hazard — a high-value community overlay.

### 3.7 Ingestion priority (recommended order)

| Priority | Source | Why first | API status |
|---|---|---|---|
| 1 | LA County Assessor parcels | Join-key backbone (APN) | ✅ REST/WFS |
| 2 | CAL FIRE DINS 2025 Palisades | Damage-status spine | ✅ REST FeatureServer |
| 3 | USGS 3DEP post-fire LiDAR | Free 3D baseline (skip a flight) | ✅ download/COPC |
| 4 | LADBS rebuild permits | Rebuild-progress signal | ⚠ endpoint to confirm |
| 5 | City GeoHub + DataLA crawl | Breadth of city layers | ✅ GeoServices + SODA |
| 6 | FEMA NFHL | Hazard overlay | ✅ REST/WMS/WFS |

---

## 4. Angle 3 — Physical & Sensor Acquisition  *(named leads; thin verification)*

> ⚠ This angle returned **named, citable leads but no 3-vote-verified claims** (except USGS LiDAR in §3.5). Treat the numbers below as planning estimates to confirm, not facts.

- **[NAMED LEAD] Drone photogrammetry / LiDAR economics:** photogrammetry ≈ **$150–$300/acre**; drone LiDAR ≈ **$150–$500/acre** (some sources cite **$30–$120/acre at scale**); operators bill **~$1,500–$3,000/day**.
  → https://www.thefuture3d.com/learn/drone-survey-cost-guide/ ; https://dronelaunchacademy.com/resources/drone-lidar-how-it-works-what-it-costs-and-how-to-get-started-2026/
- **[NAMED LEAD] LA drone regulation:** commercial flight requires **FAA Part 107**; LA airspace has significant controlled zones (LAX/Santa Monica proximity) requiring **LAANC** authorization, plus California privacy/trespass considerations.
  → https://ts2.tech/en/los-angeles-drone-laws-uncovered-the-ultimate-2025-guide-for-every-pilot/
- **[NAMED LEAD] Crowdsourced street imagery:** **Mapillary** (free, open, CV-derived map features) and **Hivemapper** (blockchain dashcam-incentive network) are the two proven models for low-cost street-level capture at neighborhood scale.
  → https://help.mapillary.com/hc/en-us/articles/360003021152-Types-of-map-data
- **[ASSESSMENT] Consumer LiDAR (iPhone/iPad Pro)** and a windshield-mounted action cam feeding a `lingbot`-style reconstruction model are the cheapest viable "drive-and-capture" rig for a small team — sub-$2k hardware. Validate accuracy against the USGS 3DEP baseline.

**Recommended posture:** ingest the *free* USGS LiDAR baseline (§3.5), then use **cheap repeatable capture** (dashcam + phone LiDAR + Mapillary upload) for the thing the baseline can't give you: **frequent change detection** during the multi-year rebuild. Reserve paid drone flights for targeted high-value blocks.

---

## 5. Angle 4 — CV/ML Pipelines: Visual → Structured Spatial  *(named leads; thin verification)*

> ⚠ The generative models (§2) are verified; the **detection/segmentation toolchain below is named-but-unverified** in this run. All are real, well-known open-source projects — validate fit against Palisades imagery.

- **[NAMED LEAD] Open-vocabulary detection — Grounding DINO** (IDEA-Research, ECCV 2024): detect arbitrary objects **by text prompt** (e.g., "burned slab," "temporary fence," "pothole," "construction dumpster") with **no retraining** — 52.5 zero-shot COCO AP. Ideal front end for OpenPali because the object catalog will keep changing through the rebuild.
  → https://github.com/IDEA-Research/GroundingDINO
- **[ASSESSMENT] Proven stack to assemble (validate each):**
  - **Detection:** YOLO (v8/v11) for known fixed classes; **Grounding DINO** for open-vocabulary.
  - **Segmentation:** **SAM / SAM 2** (Segment Anything) for instance masks, prompted by Grounding DINO boxes ("Grounded-SAM").
  - **Building footprints / rooftops:** Microsoft & Google open building-footprint datasets; geospatial foundation models **Prithvi** (NASA/IBM), **SatMAE**, **Clay** for aerial feature extraction.
  - **Damage change detection:** the **xView2/xBD** dataset + baseline is the canonical building-damage benchmark — directly fire-relevant.
    → https://xview2.org/
  - **OCR:** for permit placards / signage → structured text.
  - **Georeferencing detections:** GPS+IMU pose from the capture rig, monocular depth, or — best — the **`lingbot` 3D reconstruction** itself, which already produces camera trajectories + depth to back-project 2D detections into world coordinates.

**Recommended pipeline shape:**
`capture (video) → lingbot 3D reconstruction (depth + pose + point cloud) → Grounded-SAM detection/segmentation on frames → back-project detections to world coords via lingbot pose/depth → snap to APN parcel (§3.2) → validation gate (§2.1) → publish structured layer.`

---

## 6. Angle 5 — Platform Architecture & Business Model  *(named leads; thin verification)*

> ⚠ Named leads, not verified. Strategic guidance, validate specifics.

- **[NAMED LEAD] "Don't build your own base map."** Overture Maps Foundation argues (2026) that building a proprietary base map is now a **value trap** — the base layer is commoditized; differentiation is in fresh, deep, linked local data.
  → https://overturemaps.org/blog/2026/the-billion-dollar-data-trap-why-building-your-own-map-is-no-longer-a-viable-business-strategy/
  > **[ASSESSMENT] OpenPali's moat is the inverse of a global base map: hyperlocal depth + freshness + linkage on ONE geography.** Build *on* Overture/OSM base layers; differentiate with the Palisades-specific damage/permit/3D/change layers nobody else maintains.
- **[NAMED LEAD] Cloud-native geospatial stack:** standardize on **Cloud-Optimized GeoTIFF (COG)** for rasters, **COPC** for point clouds, **GeoParquet** for tabular/vector at scale, **PMTiles** for serverless tile delivery, **STAC** for cataloging, **Zarr** for multidimensional arrays — all enabling range-request access without a heavy server.
  → https://forrest.nyc/cloud-native-geospatial-formats-geoparquet-zarr-cog-and-pmtiles-explained/ ; https://overturemaps.org/blog/2026/02/11/stac/
  > **[ASSESSMENT] Recommended core:** PostGIS (system of record) + STAC catalog + COG/COPC/GeoParquet in object storage + PMTiles for the web map. This is cheap to operate and the industry default.
- **[NAMED LEAD] Hivemapper** demonstrates a **token-incentive model** for crowdsourced capture — a possible community-contribution mechanic for Palisades residents.
  → https://medium.com/@hilary.h.brown/case-study-reimagining-maps-through-blockchain-incentives-the-hivemapper-story
- **[ASSESSMENT] Privacy is non-optional and unverified here:** street-level imagery of private property requires **face + license-plate blurring** (the Mapillary/Google standard) and a clear policy for imagery of fire-damaged private homes — politically sensitive for this community. **Flagged as an open question (§7).**

---

## 7. Open Questions & Unverified Gaps

The research was **deliberately honest about coverage**: 24 verified claims clustered on Angles 1–2. The following need a dedicated follow-up pass before they drive spend:

1. **LADBS permit feed** — confirm the actual endpoint, format, and refresh cadence for City-of-LA / Palisades rebuild permits (§3.4). This is load-bearing and unverified.
2. **Field-acquisition economics & law** — verify drone cost ranges, Part 107/LAANC specifics for Palisades airspace, and iPhone-LiDAR accuracy vs 3DEP (§4).
3. **CV detection toolchain** — empirically validate Grounding DINO / SAM / xView2 / building-footprint models on *actual* Palisades imagery before committing the pipeline (§5).
4. **Platform & privacy** — verify the cloud-native stack choices and, critically, **design the imagery-privacy / face-plate-blurring policy** for a community whose private property was destroyed (§6).
5. **`lingbot-map` real-world performance** — the FPS/quality claims are from the repo README, unverified. Run a Palisades test drive before betting the roadmap on it (§2.4).
6. **Synthetic-data validation harness** — design the spatial-similarity gate (§2.1) that every generated/imputed layer must pass.

---

## 8. Recommended Next Actions (sequenced)

**Now (weeks):**
1. Stand up ingestion for the four ✅ verified sources: **Assessor parcels → DINS → 3DEP LiDAR → FEMA NFHL**, keyed on APN. (Pure "collect & link" — highest ROI, zero acquisition cost.)
2. Resolve the **LADBS permit feed** (close Open Question #1) and add it.
3. Read DINS field domains **live** (don't hardcode — the enumeration was refuted).

**Next (1–2 months):**
4. Prototype the **drive-and-capture** loop: dashcam + phone LiDAR → `lingbot`-style reconstruction → Grounded-SAM detection → back-project to parcels. Validate on a few blocks against 3DEP.
5. Build the **synthetic-data validation gate** (§2.1) before publishing any generated layer.

**Strategic (ongoing):**
6. Adopt the cloud-native stack (PostGIS + STAC + COG/COPC/GeoParquet + PMTiles).
7. Position the moat as **hyperlocal freshness + linkage**, built *on* Overture/OSM — not a proprietary base map.
8. Draft the **imagery-privacy policy** before any public street-level imagery ships.

---

## Appendix: Verification Ledger

- **Run:** deep-research workflow, 108 agents, 26 sources fetched, 121 claims extracted, 25 verified by 3-vote adversarial panels.
- **Confirmed (24, 3-0 votes):** all [VERIFIED] claims in §2–3.
- **Refuted (1, 0-3 votes):** exact DINS `DAMAGE`/`STRUCTURETYPE` coded-value enumeration → **read live**.
- **Coverage caveat:** Angles 3–5 returned named leads with thin verification — see §7. `lingbot-map` repo facts in §2.4 are from direct README inspection, not the verification pass.
- **Time-sensitivity:** DINS counts (12,081 / 6,845 Destroyed) and parcel counts (2,431,782) are *live and will change*. "SOTA" (DiffusionSat, EOGS) is as-of 2024–2025.
