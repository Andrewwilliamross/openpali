# OpenPali project website

The one-button introduction to OpenPali. This is a static marketing page; the map application lives in [`web/`](../web/README.md).

## Preview

From the repository root, with Python 3.12 or newer:

```sh
python3 scripts/build-site.py
python3 -m http.server 4173 --bind 127.0.0.1 --directory dist/site
```

Open <http://127.0.0.1:4173>. The page has no package dependencies, external fonts, analytics, or API calls. JavaScript only highlights nearby squares on pointer movement; the page and GitHub link work without it. The pattern is abstract branding, not recovery data.

## Publish

[Project website](../.github/workflows/pages.yml) stages a strict allowlist of files into `dist/site` and deploys it to GitHub Pages on changes to `main`. Pull requests build the artifact without deploying it. Set **Settings → Pages → Source → GitHub Actions** once in the repository.

The canonical URL and social-image URL in `index.html` are configured for <https://andrewwilliamross.github.io/openpali/>. Change them together if the domain changes. The original editable assets and raster previews are in [`assets/brand/`](../assets/brand/).

Before publishing changes, check the page at 320 px and desktop widths, keyboard focus, 200% text enlargement, reduced motion, and JavaScript disabled. Keep the primary path to GitHub obvious and retain a single call to action.
