# OpenPali project website

The Field Office is the one-button introduction to OpenPali. The map application lives in [`web/`](../web/README.md).

## Preview

From the repository root, with Python 3.12 or newer:

```sh
python3 scripts/build-site.py
python3 -m http.server 4173 --bind 127.0.0.1 --directory dist/site
```

Open <http://127.0.0.1:4173>. The page has no package dependencies, external fonts, analytics, or API calls. It uses self-hosted Fraunces and DM Sans, both under the SIL Open Font License. Font licenses are included in the staged site.

The headline and GitHub link are ordinary HTML. The three field notes use native `details` elements and work without JavaScript. A small script supplies subtle pointer motion and exclusive note opening on older browsers. Reduced motion disables movement. The first frame is the complete design.

The original paper atlas and pelican are conceptual illustrations. They contain no property data or measured geographic boundaries. See the [brand guide](../Docs/Brand/FIELD-OFFICE.md) and [asset provenance](../assets/brand/field-office/PROVENANCE.md).

## Publish

[Project website](../.github/workflows/pages.yml) stages an explicit allowlist into `dist/site`. Main-branch changes deploy to GitHub Pages. Pull requests build the artifact without deploying it. The application, generated masters, design experiments, and private operational files are excluded from the deployment.

The canonical and social-image URLs in `index.html` point to <https://andrewwilliamross.github.io/openpali/>. Change them together if the domain changes. The web images are optimized exports of the editable brand source; regenerate with [`scripts/export-field-office.cjs`](../scripts/export-field-office.cjs).

Before publishing, check desktop and 320px layouts, keyboard focus, expanded notes, 200% zoom, reduced motion, and JavaScript disabled. The canonical GitHub link is the only outbound call to action.
