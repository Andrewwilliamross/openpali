#!/usr/bin/env python3
"""Stage only the public project landing page; Python standard library only."""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "dist" / "site"
SITE_FILES = ("index.html", "style.css", "signal.js")
BRAND_FILES = (
    "fonts/DMSans.woff2", "fonts/DMSans-OFL.txt",
    "signal/favicon.svg", "signal/social-card.png", "signal/field.svg",
)


def main():
    sources = [*(ROOT / "site" / name for name in SITE_FILES),
               *(ROOT / "assets" / "brand" / name for name in BRAND_FILES)]
    missing = [str(path.relative_to(ROOT)) for path in sources if not path.is_file()]
    if missing:
        raise SystemExit("Missing site assets: " + ", ".join(missing))
    html = (ROOT / "site" / "index.html").read_text()
    marker = "<!-- OPENPALI_FIELD -->"
    if html.count(marker) != 1:
        raise SystemExit("Site HTML must contain exactly one square-field marker")
    field = (ROOT / "assets/brand/signal/field.svg").read_text()
    field = field.replace('<svg ', '<svg class="signal-svg" preserveAspectRatio="xMidYMid slice" ', 1)
    html = html.replace(marker, field)
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    (OUTPUT / "assets" / "brand").mkdir(parents=True)
    for name in SITE_FILES:
        if name == "index.html":
            (OUTPUT / name).write_text(html)
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
