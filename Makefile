.PHONY: data data-offline test web build refresh spatial dev orchestrate pmtiles publish

# ─── Orchestration (ADR 0001 — Dagster) ──────────────────────────────────────
# Lineage-tracked refresh. `make dev` opens the Dagster UI (assets, lineage,
# the oracle data-quality check); `make orchestrate` runs the full nightly job.
DAGSTER = uv run --group orchestration dagster
DEFS = orchestration/definitions.py

dev:
	cd pipeline && $(DAGSTER) dev -f $(DEFS)

orchestrate:  ## full nightly refresh (parcels + spatial backlog + tiles) via Dagster
	cd pipeline && $(DAGSTER) job execute -f $(DEFS) -j nightly_refresh

# ─── Manual CLIs (still valid; the orchestrator calls the same functions) ─────
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

# What a scheduled job runs: orchestrated refresh, then build the static site
refresh: orchestrate build

# ─── Serving (ADR 0001, Decision 5) ──────────────────────────────────────────
# Cutover sequence + safety notes: Docs/Plans/0002-serving-cutover-runbook.md
DATA_DIR  = web/public/data
TILES_DIR = web/public/tiles/palisades

pmtiles:  ## build parcels.pmtiles from the emitted GeoJSON (needs tippecanoe)
	@command -v tippecanoe >/dev/null || { echo "install tippecanoe (brew install tippecanoe)"; exit 1; }
	tippecanoe -zg --projection=EPSG:4326 -o $(DATA_DIR)/parcels.pmtiles \
		-l parcels --drop-densest-as-needed --force $(DATA_DIR)/parcels.geojson

publish:  ## sync tiles + data to the CDN bucket (needs rclone + OPENPALI_TILES_REMOTE)
	@command -v rclone >/dev/null || { echo "install rclone (brew install rclone)"; exit 1; }
	@test -n "$(OPENPALI_TILES_REMOTE)" || { echo "set OPENPALI_TILES_REMOTE=<remote:bucket/prefix>"; exit 1; }
	rclone sync $(TILES_DIR) "$(OPENPALI_TILES_REMOTE)/tiles/palisades" --progress
	rclone sync $(DATA_DIR)  "$(OPENPALI_TILES_REMOTE)/data"           --progress
