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

# 3D building scene: county building meshes, registered to lidar terrain.
# Fetches into data/raw/scene (cached, hashed); writes data/out/scene/<scene-id>.
.PHONY: scene-plan scene-build scene-verify map-perf
scene-plan:
	PYTHONPATH=pipeline pipeline/.venv/bin/python -m openpali.scene.build --plan

scene-build:
	PYTHONPATH=pipeline pipeline/.venv/bin/python -m openpali.scene.build

scene-verify:
	PYTHONPATH=pipeline pipeline/.venv/bin/python -m openpali.scene.verify

# Fly fixed camera paths over a running map and check the performance budgets.
# BASE defaults to the dev server; the container stack is http://127.0.0.1:58080.
BASE ?= http://127.0.0.1:5173
map-perf:
	node web/scripts/perf-flight.mjs --base $(BASE)

# Evidence release the map reads: build it, serve it, run the map against it.
.PHONY: evidence-build evidence-api evidence-web
evidence-build:
	PYTHONPATH=pipeline pipeline/.venv/bin/python -m openpali.intelligence.build

evidence-api:
	PYTHONPATH=pipeline pipeline/.venv/bin/python -m uvicorn openpali.api.app:app --host 127.0.0.1 --port 8000

evidence-web:
	npm --prefix web run dev
