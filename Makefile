.PHONY: data data-offline test web build refresh spatial

# Phase 2: nightly 4D spatial core (LARIAC priors -> GeoParquet/H3 store)
spatial:
	cd pipeline && uv run run_spatial.py

# Full live pipeline: fetch → score → emit → validate against official numbers
data:
	cd pipeline && uv run run.py

# Rebuild artifacts from cached responses (fast, no network)
data-offline:
	cd pipeline && uv run run.py --offline

test:
	cd pipeline && uv run pytest -q

web:
	cd web && npm run dev

build:
	cd web && npm run build

# What a scheduled job runs: refresh data, then build the static site
refresh: data build
