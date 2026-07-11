# Product and Technical Q&A

This is the living record for the production-readiness discovery conversation.

## Working method

- Codebase questions are answered from the implementation and verified behavior.
- Product questions capture the intended user experience and operating model.
- Technical preferences are treated as constraints only after their product or
  operational rationale is understood.
- Decisions, assumptions, and open questions are recorded separately.

## Product intent

- The map should become visually focused: a plain white base map plus the
  structure/rebuild layer.
- The rebuild layer should be the LiDAR/3D scan layer itself. In 2D, this should
  be a top-down view of the same scan-derived structure layer, not a separate
  parcel-first choropleth.
- The structure layer should carry the primary meaning: rebuild state should be
  encoded directly on the scan-derived structure representation.
- The base map should remain minimal but include street labels.
- The mobile experience should feel closer to Apple Maps: clean, fast,
  gesture-driven, and spatially calm rather than data-dashboard-heavy.

## Technical findings

To be established through codebase review.

## Decisions

- Prioritize a two-layer visual model for the production map:
  1. neutral white base/context map with street labels;
  2. rebuild-state LiDAR/scan structure layer, available in both top-down 2D
     and pitched 3D.

## Assumptions

None yet.

## Open questions

- Who are the primary production users, and what is the most important task the
  product must help each user complete?
- What should the product show for parcels that do not currently have LiDAR/
  splat coverage?
- Should neighborhood labels appear in the base map, or only street labels?
