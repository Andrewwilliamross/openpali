# Field Office asset provenance

Created for OpenPali in September 2026. The direction combines an original conceptual coastal atlas, archival paper, source slips, and a small working pelican. It does not depict measured geography, actual parcels, recovery status, or a physical public office.

## Illustration

The hero and three role illustrations were generated with **the built-in ImageGen tool**. The hero supplied the visual and character reference for each subsequent role. No Cua artwork, Omarchy artwork, or other project asset was copied or transformed. The full final prompt set is in [`PROMPTS.json`](PROMPTS.json).

- `hero-source.png`: original hero master, 1536 × 1024.
- `sources/follow-source.png`: pelican follows a source-card thread to a coastal sheet.
- `sources/build-tools.png`: pelican works with a pencil and drafting sheet.
- `sources/correct-record.png`: pelican inserts an annotation slip into an open folder.
- `hero.webp` and `hero-900.webp`: encoded web exports of the hero.
- Three root-level role PNGs: 640px-wide encoded display exports. Masters remain unchanged.

These are generated editorial illustrations, not Blender renders or photographs. The alternate Living Atlas uses actual Three.js geometry; its medium and sources are documented separately in `design-lab/round-2/atlas/`.

## Typography

Self-hosted variable fonts, subset to the page's Latin characters and punctuation:

- [Fraunces](https://github.com/google/fonts/tree/main/ofl/fraunces), by Undercase Type. SIL Open Font License 1.1 in `fonts/Fraunces-OFL.txt`.
- [DM Sans](https://github.com/google/fonts/tree/main/ofl/dmsans). SIL Open Font License 1.1 in `fonts/DMSans-OFL.txt`.

The exact font files are checked in. Fraunces uses optical size 144, weight 450, softness 35, and WONK 1 for the exported headline. `type-outlines.json` preserves the source glyph paths for static assets. It can be rebuilt with `scripts/generate-field-office-type.py` using FontTools and Brotli. The live website retains real HTML text.

## Vector and layout source

The pelican icon, favicon, wordmark composition, sticker, and banner/social layouts are original project vector/code artwork. `scripts/export-field-office.cjs` contains their editable layout and exports. Wordmark and headline glyphs use the included Fraunces outlines. Small raster-export captions use Arial. The website uses self-hosted DM Sans.

Run the exporter from the repository root with Node and `sharp` available:

```sh
node scripts/export-field-office.cjs
```

It performs no network calls. It writes the PNG/SVG/WebP exports and a byte-size manifest. For a separate installed Sharp directory, use Node's `NODE_PATH` environment variable. Changing illustration content requires a new art source; the exporter only lays out and encodes the approved artwork.

## Reference research

Design principles and critiques are documented in `design-lab/round-2/RESEARCH.md` and `STRATEGY.md`. References include [Cua](https://cua.ai/), [Cua's repository](https://github.com/trycua/cua), [Omarchy](https://omarchy.org/), [Prime Agent](https://github.com/PrimeIntellect-ai/prime-agent), and [GeoLibre](https://github.com/opengeos/GeoLibre). They inform the breadth and consistency of the identity, rather than supply its assets.

The project owner has not yet selected a source-code license. Font license notices do not license the repository or imply that another project's license applies to these assets.
