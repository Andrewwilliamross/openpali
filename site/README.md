# OpenPali project website

The website introduces OpenPali as a platform for integrating siloed records, geospatial data, and imagery to analyze the Palisades rebuild. It uses the **Signal** identity: white, cobalt, DM Sans, and a scattered square field. The application lives in [`web/`](../web/README.md).

## Preview

From the repository root, with Python 3.12 or newer:

```sh
python3 scripts/build-site.py
python3 -m http.server 4173 --bind 127.0.0.1 --directory dist/site
```

Open <http://127.0.0.1:4173>. The build inserts the committed square-field SVG at `<!-- OPENPALI_FIELD -->` in `index.html`. Its allowlist stages eight files plus `.nojekyll`: HTML, CSS, JavaScript, DM Sans and its license, favicon, social preview, and field SVG.

The site needs no rendering package, map service, or external font request. The headline, platform description, GitHub action, and credit are ordinary HTML. The square field is decorative and stays visible with JavaScript disabled.

## The field

646 independent squares stay on a fixed grid. A fine pointer makes nearby squares slightly larger and more opaque; their centers never move. There is no letter-forming state or layout toggle. Touch and reduced-motion preferences keep the field still. Rendering stops when the hover effect settles, and hidden/offscreen scenes reset their emphasis.

The shared coordinates and asset generator are in [`assets/brand/signal/`](../assets/brand/signal/). Static branding and the website use the same field. See the [brand guide](../Docs/Brand/README.md) for export steps and the [review notes](../design-lab/round-4/README.md) for checks.

## Build and release

The [Pages workflow](../.github/workflows/pages.yml) builds pull requests and deploys eligible main-branch revisions. The application, raw data, design studies, and authoring tools stay outside the deployment allowlist.

Canonical and social URLs target <https://andrewwilliamross.github.io/openpali/>. Update them together if the domain changes. The GitHub repository social preview is a separate setting from the website metadata.

Before release, check desktop and mobile layout, keyboard focus, pointer response, reduced motion, and the no-JavaScript fallback. Earlier designs are preserved in the [design lab](../design-lab/README.md).
