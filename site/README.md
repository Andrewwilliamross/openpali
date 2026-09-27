# OpenPali project website

**Field Notes** is the current website candidate in [PR #12](https://github.com/Andrewwilliamross/openpali/pull/12). It has one primary GitHub action, a flat pelican with a notebook, and a close drawing of actual Palisades parcels. This revision is pending review; these files do not establish that it is published on main. The map application lives in [`web/`](../web/README.md).

## Preview

From the repository root, with Python 3.12 or newer:

```sh
python3 scripts/compose-field-notes.py
python3 scripts/build-site.py
python3 -m http.server 4173 --bind 127.0.0.1 --directory dist/site
```

Open <http://127.0.0.1:4173>. The composer rebuilds [`scene.svg`](../assets/brand/field-notes-2d/scene.svg) from the pelican rig and the committed parcel drawing. The build inserts that SVG at `<!-- OPENPALI_DRAWING -->` in `index.html`.

Both scripts use the Python standard library. The page uses local Fraunces and DM Sans files, has no runtime package dependencies, and makes no automatic external data or font requests. Its deployment allowlist contains **10 source files**, plus the generated `.nojekyll` marker: HTML, CSS, JavaScript, two fonts and their notices, favicon, social preview, and scene SVG.

## Scene and controls

A 26-second loop takes the pelican through a planted waddle, inspection, pencil lift, margin-note underline, and return. The parcel geometry remains fixed. **Pause motion / Resume motion** stops and continues the shared animation clock. Hidden tabs and offscreen scenes suspend it.

Reduced-motion mode starts with a complete still and offers an explicit **Play once** action. After one cycle it returns to the still. With JavaScript disabled, the drawing, project text, GitHub link, source disclosure, and native field notes remain available. Opening a field note with JavaScript enabled also emphasizes a corresponding margin detail.

The drawing uses 61 County parcel features around Galloway and Hartzell Streets at Bestor Boulevard. The pelican and separate architectural margin study are illustrative. See [geography and source terms](../design-lab/round-3/GEOGRAPHY.md); the artwork carries no property-status or approved-plan claims.

## Build and release

The [Pages workflow](../.github/workflows/pages.yml) builds pull requests without deploying them. Eligible main-branch runs deploy the staged site. Application code, source data, design studies, and artwork masters are outside the allowlist.

The canonical URL and social URL in `index.html` use <https://andrewwilliamross.github.io/openpali/>. Update them together if the domain changes. See the [brand kit](../Docs/Brand/README.md) for static-asset exports.

Before release, inspect the full loop at desktop and phone widths, keyboard focus, expanded notes, pause/resume, reduced-motion playback, hidden/offscreen suspension, and the no-JavaScript still. The previous paper-atlas website is archived in [`design-lab/round-2/field-office/`](../design-lab/round-2/field-office/).
