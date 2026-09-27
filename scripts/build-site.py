#!/usr/bin/env python3
"""Stage only the public project landing page; Python standard library only."""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "dist" / "site"
SITE_FILES = ("index.html", "style.css", "grid.js")
BRAND_FILES = ("mark.svg", "favicon.svg", "social-card.png")


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
        shutil.copyfile(ROOT / "site" / name, OUTPUT / name)
    for name in BRAND_FILES:
        shutil.copyfile(ROOT / "assets" / "brand" / name, OUTPUT / "assets" / "brand" / name)
    (OUTPUT / ".nojekyll").touch()
    print(f"Staged {len(sources)} files at {OUTPUT}")


if __name__ == "__main__":
    main()
