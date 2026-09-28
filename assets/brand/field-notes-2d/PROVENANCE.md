# Field Notes artwork

The pelican is original SVG path artwork created for OpenPali. Its rounded ink outline, held field notebook, webbed feet, and pencil form a rig for the website animation. The avatar and small head favicon are derivatives of that character. No reference-project artwork or raster generation is embedded in this family.

The scene, banner, and social card contain actual Los Angeles County parcel and street geometry. The source is the general parcel service, without damage or recovery filtering. The 61-parcel crop covers Galloway and Hartzell Streets near Bestor Boulevard. Source responses, exact coordinates, query descriptions, hashes, and reuse terms are retained in [map/close/provenance.json](map/close/provenance.json) and [the geography notes](../../../design-lab/round-3/GEOGRAPHY.md).

The bird, pencil gesture, and separate plan/elevation sketches are illustrative. The architectural inset describes no real building or proposal. The parcel paths remain fixed throughout the animation. County attribution is present in the artwork and website source disclosure; the project is independent.

Fraunces and DM Sans are bundled under the SIL Open Font License in the adjoining [font directory](../field-office/fonts/). Banner and social lettering is outlined. The live website uses the font files.

## Rebuild

- `python3 scripts/compose-field-notes.py` composes `scene.svg` with the Python standard library.
- `generate-assets.py` rebuilds avatar, banner, social-card, and favicon SVGs; it requires FontTools with WOFF2 support.
- `export-assets.cjs` rasterizes the SVG exports with Sharp.
- `python3 scripts/build-site.py` stages the website from the committed source assets. It does not fetch geographic data or install rendering dependencies.

This provenance note does not grant a source-code, artwork, or trademark license. The repository's current licensing notice and the County's separate data terms apply.
