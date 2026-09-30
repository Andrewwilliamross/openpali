# Visual intelligence: measurement and acquisition program

This is the implementation design accompanying the [data expansion](2026-09-24-DATA-EXPANSION.md).
Verified sources and experiments are labeled below. Current-site predictions
and new aerial/ground surveys have not yet been produced.

## Questions the system must answer

At an identified building/site and date: are debris, exposed foundations,
excavation, erected framing, roof cover, exterior enclosure, access works or
retained features visible? What changed since the previous usable observation?
Which part of the property could the sensor actually see? How sure are we?

These components can coexist. A retained foundation, a new ADU and an old
standing garage cannot be represented accurately by one parcel-wide stage.
Photographs cannot establish concealed structural compliance, safe soil,
energized utilities, occupancy authorization or actual resident return.

## 1. Acquire complementary modalities

| Modality | Data delivered | Measurements to attempt | Acquisition/quality decision |
|---|---|---|---|
| Cleanup packets | PDF pages, extracted RGB photographs and checklist evidence | Retained slabs/walls/pools, capped utilities, grading, fencing and debris at clearance time | **12 PDFs acquired**, 1–9 pages each. Determine document class first; withdrawal forms are not completed clearance packets. Preserve page/image provenance and uncertain photo dates. |
| Public classified LiDAR | LAZ files containing measured XYZ, intensity, return information and class labels; terrain/surface rasters | Ground slope, elevation, residual walls/trees, height and volume above terrain | **541-tile catalog verified** for the January 21, 2025 flight. The formal project report describes classified LAZ 1.4, 0.5 m terrain/intensity and 1 m maximum-height products. Emergency 0.5 m DSMs are a separate product family. |
| Dated nadir and oblique aerials | Georeferenced pixels and camera/capture metadata, including side views | Building footprint, slab/roof cover, wall/framing presence, street works | Catalog actual capture footprints/dates first. Select oblique imagery where vertical structure matters. A painted rendering or pre-fire listing photo is not observed rebuilding. |
| Satellite archive/tasking | Multispectral/panchromatic rasters; optional stereo capture | Neighborhood-scale clearance, large roof/slab changes, vegetation and recurring broad coverage | Planet documents 50 cm delivered SkySat sampling and stereo tasking. Treat delivery sampling separately from native resolving power. Thin framing members require closer imagery; tasking is not yet ordered. |
| Repeat street/360 photography | Geolocated RGB/video with timestamps, headings and route trace | Facade/framing progress, equipment, site access, visible utility works, obstruction | User-driven survey can fill specific coverage gaps. Capture consistent frontage/left/right views from public access; blur incidental faces/plates in public artifacts. Retain occlusion and geolocation error. |
| Targeted drone photogrammetry | Overlapping nadir/oblique photographs, calibrated cameras, surveyed control, orthomosaic, dense cloud/mesh | Height/volume change, roof/facade cover and site grading | Proposed pilot target: approximately 2–5 cm ground sampling where feasible, plus independent checkpoints. Have a qualified operator design authorized capture. Actual metric accuracy must be measured, not assumed from pixel size or RTK branding. |
| Targeted survey/mobile LiDAR | Calibrated point clouds and registration/control observations | Ground/retaining-wall geometry and areas poorly reconstructed from photographs | Use selectively when it answers a measurement question RGB cannot. A consumer phone scan and an airborne survey have different range/accuracy/occlusion limits. |
| Multispectral/thermal context | Calibrated spectral or temperature-related measurements | Vegetation condition, exposed surfaces and narrowly defined inspected anomalies | Use only with a defined measurement/evaluation protocol. Thermal appearance does not prove an energized connection or hidden construction quality. Sentinel-scale pixels provide broader fuel context, not individual framing inspections. |

Primary references: [USGS emergency products](https://www.usgs.gov/3d-elevation-program/science/2025-post-wildfire-lidar-data-los-angeles-ca),
[formal Palisades LiDAR project report](https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/metadata/CA_2025LosAngelesPostWildfire_C25/CA_LAPostWildfire_Palisades_C25/reports/CA_LAPostWildfire_Palisades_WU300865_Report.pdf),
[Planet imagery specification](https://docs.planet.com/data/imagery/skysat/),
[tasking modes](https://docs.planet.com/platform/get-started/access-data/task-imagery/create_orders/),
[OpenDroneMap accuracy workflow](https://docs.opendronemap.org/te/map-accuracy/).

### A concrete LiDAR acquisition finding

The catalog sums to approximately 11.55 billion points. The tile containing
677 Via de la Paz has **20,118,164 points** and an approximately 83.6 MB LAZ
object. The VPC's relative S3 asset link returned 404; the official download
manifest supplied a working USGS delivery-host link. The full tile was acquired,
all 20,118,164 points were read, and **52,808 points** were extracted within the
parcel plus a five-meter context buffer. The saved LAZ was reopened to verify
its point count. The [acquisition manifest](2026-09-24-visual-baseline.json)
records hashes, source paths and the crop/preview paths.

This crop has 23,454 ground-class points, 29,097 unclassified points and 257
low-noise-class points. “Classified LiDAR” does not mean labeled roofs or framing:
the sample does not contain those ready-made semantic labels. The preview shows
the raw returns for QA, including the source noise class. Production measurement
must apply quality/withheld/overlap filtering and validate its own semantic labels.

The catalog `datetime` and LAS file-creation date say March 25, 2025, while the
project report establishes the **January 21 acquisition**. The VPC was modified
again in September 2026. None of those processing/publication timestamps makes
the measured scene a 2026 observation. Retain the discrepancy explicitly.

The report describes average first-return density of 37.2 points/m² across the
survey. That is a project-level summary, not guaranteed local ground density.
Download only the tiles needed for a pilot; retain the official classification,
withheld/overlap flags and vertical reference. A limited header read may omit
the extended coordinate-reference record; use the complete metadata/report.

## 2. A pipeline that can produce defensible physical observations

1. **Catalog:** scene footprint, asset checksum, capture interval, sensor,
   original/delivered resolution, camera model, coordinate/vertical reference,
   licensing/use fields and quality/coverage masks. Reuse CVP's inspected
   provenance and capability contracts, adapting them to OpenPali IDs.
2. **Register:** align dates using stable roads/control features. Independently
   measure residual positional error. Orthorectify and account for roof-to-ground
   displacement in oblique images. A one-pixel translation must not become a
   new wall or a parcel-boundary change.
3. **Measure visibility:** masks for clouds, smoke, shadows, trees, foreground
   occlusion, off-frame areas and usable ground sampling. Retain `unobservable`
   independently of the predicted physical class.
4. **Create candidate measurements:** semantic masks for ground/debris/slab/
   wall-frame/roof/vegetation; building-instance footprints; point-cloud
   height-above-ground and density; terrain/volume change where registration
   uncertainty allows it. Preserve estimates and uncertainty, not just class IDs.
5. **Associate:** attach candidates to structure/project footprints within a
   versioned parcel. Model visible retained structures and new structures
   independently. Border ambiguities go to review.
6. **Fuse over time:** combine visual likelihoods with dated agency/document
   assertions in a model allowing overlapping work and reversals. Physical
   completion is interval-censored between observations; do not invent an exact
   construction date. Correlated photographs from the same visit are one source
   episode, not many independent confirmations.
7. **Review and publish:** show the source crop, masks/change overlay, capture
   date, missing viewpoints, model version and supporting record. A measured
   cloud or SfM mesh may support measurements; a Gaussian-splat rendering is
   primarily an inspection/viewing artifact unless its geometry is validated.

[TorchGeo](https://github.com/torchgeo/torchgeo) is suitable for aligned
geospatial sampling, raster datasets and training infrastructure. OpenDroneMap
provides a photogrammetry route. Start with a supervised segmentation/change
baseline and inspect foundation-model proposals as candidate labels. Select
models by a local benchmark rather than reputation or a generic “SOTA” claim.
Use point-cloud tooling already available in the Python stack before adding a
new service for every modality.

## 3. Pilot and acceptance criteria

**Proposed pilot:** 240 sites across private/government cleanup, flat/hillside
lots, standing homes, major rebuild phases, multiple structures, shadows and
occluded sites. Include 60 randomly selected sites to measure population error;
use the remaining 180 to cover difficult/valuable states. At least three dated
observation episodes where available. Lack of temporal coverage is a result,
not a reason to substitute undated images.

- Two independent annotators label observable components, occlusion and
  disagreement; adjudicate differences. Do not use a permit milestone as a
  perfect physical label. Associate inspections only within their work scope.
- Reserve whole streets/blocks and later capture dates for evaluation. Images
  from the same property or capture episode cannot cross split boundaries.
- Compare agency-only, imagery-only and fused approaches; run modality ablations.
  Evaluate whether the added data actually improves the decision being made.
- Report per-class precision/recall, false-change rate, area/height error,
  temporal interval coverage, calibration and abstention by geography/modality.
  A roof detector with high average accuracy but frequent false roofs on empty
  lots is unacceptable for a homeowner-facing claim.
- Initial proposed release gate for a displayed positive component: at least
  95% measured precision on the held-out set, its confidence interval, adequate
  support per class, and explicit unknown/occluded handling. Revisit thresholds
  using measured error costs; this is an acceptance target, not current performance.
- Registration/control errors and temporal mismatch must be substantially
  smaller than the physical change claimed. Report them alongside area/height
  measurements. No fabricated high-resolution detail or generative fill may
  serve as evidence.

## 4. Choose the next observation deliberately

Queue records contain: parcel/project, unresolved question, current evidence,
last usable date, required view/resolution, source attempts, expected decision
impact, candidate acquisition cost, and successful-resolution criterion.

Prioritize expected uncertainty reduction × decision importance per acquisition
cost, while reserving a random audit allocation and geographic coverage. Batch
nearby field stops and satellite/aerial coverage rather than ordering one image
per property. The exported 20-site private-cleanup sample is the first concrete
input; it is not yet an optimized route or proof that a field visit is necessary.

Before commissioning capture, produce an acquisition card with the exact AOI,
questions, views, date window, expected deliverables and quote. No purchase is
required to start the public LiDAR/document/field-queue work already performed.
