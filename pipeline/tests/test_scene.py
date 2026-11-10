"""Scene build: quantization, terrain compositing and naming, without the network."""
import numpy as np
import pytest

from openpali.scene import build, sources, terrain as terrain_module
from openpali.scene.terrain import BLEND_M, Terrain, bilinear, decode_terrarium, encode_terrarium


def oct_decode(pairs: np.ndarray) -> np.ndarray:
    xy = pairs.astype(np.float64) / 127
    z = 1 - np.abs(xy).sum(axis=1)
    folded = (1 - np.abs(xy[:, ::-1])) * np.where(xy >= 0, 1.0, -1.0)
    xy = np.where((z < 0)[:, None], folded, xy)
    out = np.column_stack([xy, z])
    return out / np.linalg.norm(out, axis=1, keepdims=True)


def test_octahedral_normals_round_trip_within_a_degree():
    rng = np.random.default_rng(7)
    normals = rng.normal(size=(2000, 3))
    normals /= np.linalg.norm(normals, axis=1, keepdims=True)
    decoded = oct_decode(build.oct_encode(normals))
    assert (decoded * normals).sum(axis=1).min() > np.cos(np.radians(1.0))


def test_quantize_is_within_one_grid_step_and_16_bytes():
    rng = np.random.default_rng(3)
    local = rng.uniform([-900, 200, 40], [1800, 2600, 310], size=(500, 3))
    normals = np.tile([0.0, 0.0, 1.0], (500, 1))
    vertices, grid = build.quantize(local, normals, rng.uniform(size=(500, 2)), rng.integers(1, 9000, 500))
    assert vertices.dtype.itemsize == build.VERTEX_BYTES == 16
    restored = np.asarray(grid['min']) + vertices['pos'] / 65535 * np.asarray(grid['extent'])
    assert np.abs(restored - local).max() <= max(grid['extent']) / 65535
    assert max(grid['extent']) / 65535 < 0.05  # centimetres, not decimetres


def test_usgs_tile_names_match_the_published_convention():
    assert sources.usgs_tile_name(358500 // 750, 3767250 // 750) == 'Prelim_11SLT003585037672'
    assert sources.usgs_tile_name(359250 // 750, 3768000 // 750) == 'Prelim_11SLT003592037680'


def test_terrarium_round_trip_is_within_its_quantum():
    height = np.random.default_rng(1).uniform(-20, 900, (256, 256))
    assert np.abs(decode_terrarium(encode_terrarium(height)) - height).max() <= 1 / 512 + 1e-9


def test_bilinear_interpolates_and_clamps():
    grid = np.arange(12.0).reshape(3, 4)
    assert bilinear(grid, np.array([0.5]), np.array([1.5]))[0] == pytest.approx(3.5)
    assert bilinear(grid, np.array([-4.0]), np.array([9.0]))[0] == 3.0


@pytest.fixture
def lidar(monkeypatch):
    """One acquired lidar tile at 250 m over regional terrain at 200 m."""
    t = Terrain({}, offline=True)
    tile = (478, 5023)
    t.available.add(tile)
    raster = np.full((1500, 1500), 250.0, dtype=np.float32)
    raster[:20, :20] = np.nan  # a void in the north-west corner
    monkeypatch.setattr(t, '_raster', lambda _tile: raster)
    monkeypatch.setattr(t, 'sample_mapzen', lambda lon, lat: np.full(np.shape(lon), 200.0))
    import pyproj
    to_lonlat = pyproj.Transformer.from_crs(6340, 4326, always_xy=True)

    def at(east_offset: float, north_offset: float):
        return to_lonlat.transform(tile[0] * 750 + east_offset, tile[1] * 750 + north_offset)
    return t, at


def test_composite_is_lidar_inside_and_regional_outside(lidar):
    t, at = lidar
    inside, weight = t.sample(*[np.array([v]) for v in at(375, 375)])
    assert inside[0] == pytest.approx(250.0) and weight[0] == 1
    outside, weight = t.sample(*[np.array([v]) for v in at(-100, 375)])
    assert outside[0] == pytest.approx(200.0) and weight[0] == 0


def test_composite_feathers_toward_sides_without_a_neighbour(lidar):
    t, at = lidar
    edge, weight = t.sample(*[np.array([v]) for v in at(BLEND_M / 2, 375)])
    assert weight[0] == pytest.approx(0.5, abs=0.02)
    assert edge[0] == pytest.approx(225.0, abs=1.0)
    # with the western neighbour acquired, the shared edge is not feathered
    t.available.add((477, 5023))
    _, weight = t.sample(*[np.array([v]) for v in at(BLEND_M / 2, 375)])
    assert weight[0] == 1


def test_lidar_voids_fall_back_to_regional_terrain(lidar):
    t, at = lidar
    void, weight = t.sample(*[np.array([v]) for v in at(3, 747)])
    assert weight[0] == 0 and void[0] == pytest.approx(200.0)


def test_bake_skips_tiles_the_lidar_does_not_touch(lidar):
    t, _ = lidar
    assert t.bake(16, 100, 100) is None
    assert terrain_module.BAKE_ZOOMS[-1] == 16
