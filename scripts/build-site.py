#!/usr/bin/env python3
"""Stage only the public project landing page; Python standard library only."""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "dist" / "site"
SITE_FILES = ("index.html", "style.css", "field-office.js")
BRAND_FILES = tuple("field-office/fonts/" + name for name in (
    "Fraunces.woff2", "DMSans.woff2", "Fraunces-OFL.txt", "DMSans-OFL.txt",
)) + tuple("field-notes-2d/" + name for name in (
    "favicon.svg", "social-card.png", "scene.svg",
))


def main():
    sources = [*(ROOT / "site" / name for name in SITE_FILES),
               *(ROOT / "assets" / "brand" / name for name in BRAND_FILES)]
    missing = [str(path.relative_to(ROOT)) for path in sources if not path.is_file()]
    if missing:
        raise SystemExit("Missing site assets: " + ", ".join(missing))
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    (OUTPUT / "assets" / "brand").mkdir(parents=True)
    for name in SITE_FILES:
        if name == "index.html":
            html = (ROOT / "site" / name).read_text()
            marker = "<!-- OPENPALI_DRAWING -->"
            if html.count(marker) != 1:
                raise SystemExit("Site HTML must contain exactly one drawing marker")
            scene = (ROOT / "assets/brand/field-notes-2d/scene.svg").read_text()
            (OUTPUT / name).write_text(html.replace(marker, scene))
        else:
            shutil.copyfile(ROOT / "site" / name, OUTPUT / name)
    for name in BRAND_FILES:
        destination = OUTPUT / "assets" / "brand" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / "assets" / "brand" / name, destination)
    (OUTPUT / ".nojekyll").touch()
    print(f"Staged {len(sources)} files at {OUTPUT}")


if __name__ == "__main__":
    main()
