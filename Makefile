.PHONY: data data-offline test web build refresh spatial

# Phase 2: nightly 4D spatial core (LARIAC priors -> GeoParquet/H3 store)
spatial:
	cd pipeline && uv run run_spatial.py

# Static civic pipeline: fetch → normalize evidence → validate → emit
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

# Verified portable research release; independent of the production pointer.
.PHONY: evidence-build evidence-api evidence-web evidence-import
evidence-build:
	PYTHONPATH=pipeline pipeline/.venv/bin/python -m openpali.intelligence.build

evidence-api:
	PYTHONPATH=pipeline OPENPALI_LOCAL_WORKSPACE=1 pipeline/.venv/bin/python -m uvicorn openpali.api.app:app --host 127.0.0.1 --port 8000

evidence-web:
	npm --prefix web run dev

evidence-import:
	PYTHONPATH=pipeline pipeline/.venv/bin/python -m openpali.intelligence.import_ledger
