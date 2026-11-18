"""Imagery mirror and roof images, without the network."""
import io

import pytest
from PIL import Image

from openpali.scene import imagery
from openpali.scene.sources import Missing


def png(colour) -> bytes:
    out = io.BytesIO()
    Image.new('RGB', (256, 256), colour).save(out, 'PNG')
    return out.getvalue()


@pytest.fixture
def vendor(tmp_path, monkeypatch):
    """A vendor whose tiles are flat colours; `absent` tiles answer 404."""
    absent: set[tuple[int, int, int]] = set()

    def tile(z, x, y, *, offline=False):
        if (z, x, y) in absent:
            raise Missing(f'{z}/{x}/{y}')
        return png((x % 256, y % 256, z))
    monkeypatch.setattr(imagery, 'tile', tile)
    monkeypatch.setattr(imagery, 'OUT', tmp_path)
    return absent


def test_block_writes_the_top_zoom_and_derives_the_zooms_above_it(vendor, tmp_path):
    written, missing, size = imagery.mirror_block(5, 9, offline=False)
    assert (written, missing) == (16 + 4 + 1, 0) and size > 0
    for z, count in ((20, 16), (19, 4), (18, 1)):
        files = list((tmp_path / imagery.LAYER / str(z)).rglob('*.webp'))
        assert len(files) == count
        assert Image.open(files[0]).size == (256, 256)
    assert (tmp_path / imagery.LAYER / '20' / '20' / '36.webp').exists()
    # a finished block is not fetched again
    assert imagery.mirror_block(5, 9, offline=False) == (0, 0, 0)


def test_block_with_a_source_hole_is_left_to_the_vendor(vendor, tmp_path):
    vendor.add((20, 21, 37))
    written, missing, _ = imagery.mirror_block(5, 9, offline=False)
    assert (written, missing) == (15, 1)
    assert not (tmp_path / imagery.LAYER / '18').exists()


def test_ancestors_cover_every_coarser_zoom_once():
    low = imagery.ancestors([(8, 8), (9, 8)])
    assert [t for t in low if t[0] == 17] == [(17, 4, 4)]
    assert {z for z, _, _ in low} == set(range(imagery.MIN_ZOOM, imagery.COVER_ZOOM))


def test_roof_image_stitches_the_rectangle_and_keeps_holes_transparent(vendor):
    whole = Image.open(io.BytesIO(imagery.atlas(18, 10, 20, 3, 2)))
    assert whole.size == (768, 512) and whole.mode == 'RGB'
    vendor.add((18, 11, 20))
    holed = Image.open(io.BytesIO(imagery.atlas(18, 10, 20, 3, 2))).convert('RGBA')
    assert holed.getpixel((256 + 128, 128))[3] == 0 and holed.getpixel((128, 128))[3] == 255
    # wider than the cap: tiles shrink so the image stays within it
    assert Image.open(io.BytesIO(imagery.atlas(18, 0, 0, 12, 1))).width == 12 * (2048 // 12)
    vendor.update((18, x, 0) for x in range(2))
    assert imagery.atlas(18, 0, 0, 2, 1) is None
