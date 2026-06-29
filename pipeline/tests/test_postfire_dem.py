"""Phase 1 terrain-ingestion guardrails: terrarium encode/decode, footprint
derivation, build-plan + manifest correctness, and the heavy-step isolation."""

from __future__ import annotations

import dataclasses
import json

import numpy as np
import pytest

from core.spatial import postfire_dem as pd
from core.spatial.baselines import PALISADES_POSTFIRE_DEM


# ---------------------------------------------------------------------------
# terrarium encode / decode
# ---------------------------------------------------------------------------


def test_terrarium_round_trip_within_quantization():
    elev = np.array([-413.0, -10.0, 0.0, 0.5, 36.193, 250.75, 1500.0, 3000.0])
    rgb = pd.encode_terrarium(elev)
    assert rgb.dtype == np.uint8
    back = pd.decode_terrarium(rgb)
    # terrarium carries a 1/256 m fractional channel
    np.testing.assert_allclose(back, elev, atol=1.0 / 256.0)


def test_terrarium_known_value():
    # 0 m -> v = 32768 -> r=128, g=0, b=0
    rgb = pd.encode_terrarium(np.array([0.0]))
    np.testing.assert_array_equal(rgb[0], [128, 0, 0])
    assert pd.decode_terrarium(np.array([[128, 0, 0]]))[0] == 0.0


# ---------------------------------------------------------------------------
# burn footprint
# ---------------------------------------------------------------------------


def test_burn_footprint_bounds(tmp_path):
    fc = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "geometry": {
                "type": "Polygon",
                "coordinates": [[[-118.55, 34.03], [-118.54, 34.03],
                                 [-118.54, 34.05], [-118.55, 34.05], [-118.55, 34.03]]]}},
            {"type": "Feature", "geometry": {
                "type": "Point", "coordinates": [-118.50, 34.10]}},
            {"type": "Feature", "geometry": None},  # null geom is skipped
        ],
    }
    p = tmp_path / "parcels.geojson"
    p.write_text(json.dumps(fc))
    b = pd.burn_footprint_bounds(p)
    assert b == pytest.approx((-118.55, 34.03, -118.50, 34.10))


def test_burn_footprint_bounds_empty_raises(tmp_path):
    p = tmp_path / "empty.geojson"
    p.write_text(json.dumps({"type": "FeatureCollection", "features": []}))
    with pytest.raises(ValueError, match="footprint"):
        pd.burn_footprint_bounds(p)


# ---------------------------------------------------------------------------
# build plan + manifest
# ---------------------------------------------------------------------------


def test_plan_reconciles_navd88_to_ellipsoidal():
    plan = pd.plan_terrain_build(web_tiles_url="https://cdn.x/dtm/{z}/{x}/{y}.png")
    assert plan.source_hcrs == "EPSG:6340"  # NAD83(2011)/UTM 11N
    assert plan.source_vcrs == "EPSG:5703"  # NAVD88/GEOID18
    assert plan.target_tile_crs == "EPSG:3857"
    assert "ellipsoidal" in plan.target_vdatum.lower()
    assert plan.encoding == "terrarium"
    assert plan.maxzoom > plan.minzoom
    assert plan.bounds == pd.PALISADES_DEM_BOUNDS_WGS84
    assert plan.doi == PALISADES_POSTFIRE_DEM.doi
    assert plan.preliminary is True


def test_plan_rejects_unexpected_vertical_datum():
    # a baseline that is NOT NAVD88/GEOID18 must not flow through this path
    wrong = dataclasses.replace(PALISADES_POSTFIRE_DEM, vertical_epsg=4979)
    with pytest.raises(ValueError, match="5703"):
        pd.plan_terrain_build(web_tiles_url="x", baseline=wrong)


def test_terrain_manifest_mirrors_web_config_and_carries_provenance():
    plan = pd.plan_terrain_build(web_tiles_url="https://cdn.x/dtm/{z}/{x}/{y}.png")
    m = pd.terrain_manifest(plan)
    # the fields lib/terrain.ts TerrainConfig consumes
    for key in ("tiles", "encoding", "tileSize", "minzoom", "maxzoom", "bounds",
                "attribution", "vdatum"):
        assert key in m, f"manifest missing web TerrainConfig field {key}"
    assert m["bounds"] == list(pd.PALISADES_DEM_BOUNDS_WGS84)
    # provenance so a preliminary, supersedable source is never mistaken for final
    assert m["provenance"]["doi"] == PALISADES_POSTFIRE_DEM.doi
    assert m["provenance"]["preliminary"] is True
    assert m["provenance"]["doi_url"].endswith(PALISADES_POSTFIRE_DEM.doi)


def test_write_terrain_manifest(tmp_path):
    plan = pd.plan_terrain_build(web_tiles_url="https://cdn.x/dtm/{z}/{x}/{y}.png")
    out = tmp_path / "tiles" / "terrain.json"
    pd.write_terrain_manifest(plan, out)
    assert json.loads(out.read_text())["encoding"] == "terrarium"


# ---------------------------------------------------------------------------
# heavy step isolation
# ---------------------------------------------------------------------------


def test_generate_terrain_tiles_fails_loudly_without_toolchain():
    plan = pd.plan_terrain_build(web_tiles_url="x")
    # the raster toolchain is intentionally absent from the core deps
    with pytest.raises((RuntimeError, NotImplementedError)) as exc:
        pd.generate_terrain_tiles(plan)
    assert "gdal" in str(exc.value).lower() or "raster" in str(exc.value).lower()


def test_validate_footprint_datum_undulation_is_la_plausible():
    try:
        und = pd.validate_footprint_datum()
    except RuntimeError as e:  # GEOID18 grid unavailable offline
        pytest.skip(f"GEOID18 grid unavailable: {e}")
    assert -40.0 < und < -30.0, f"footprint undulation {und:.2f} m not LA-plausible"
