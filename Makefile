.PHONY: data data-offline test web build refresh

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
