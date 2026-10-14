"""The droop family: printable strands, and the print-verified laws."""
import math

import numpy as np
import pytest

from text2print import build, droop, printer
from text2print.shapes import SHAPES

SMALL = {"cup": {"diameter": 60, "height": 70}, "bowl": {"diameter": 100, "height": 50},
         "vase": {"diameter": 80, "height": 100}, "goblet": {"diameter": 90, "height": 100},
         "candle": {"diameter": 90, "height": 90}}


@pytest.mark.full
@pytest.mark.parametrize("shape", list(SMALL))
@pytest.mark.parametrize("style", list(droop.STYLES))
def test_every_shape_and_style_is_one_watertight_body(shape, style):
    b = build.make(shape, style, SMALL[shape])
    m = b.parts[0][1]
    assert m.is_watertight and len(m.split(only_watertight=False)) == 1
    assert b.stats["strands"] > 0 and b.preview is not None


@pytest.mark.parametrize("style", list(droop.STYLES))
def test_strands_never_share_layers_where_they_overlap(style):
    nz = printer.nozzle(0.4); S = SHAPES["vase"]; v = S.defaults(); prof = S.profile(v)[0]
    q = lambda z: (math.floor(z / nz.layer_h) + 0.25) * nz.layer_h
    spots = droop._never_touch(droop._rows(style, prof, v["height"], nz, 1.45, 1.4), prof, q)
    for i, a in enumerate(spots):
        for b in spots[i + 1:]:
            if abs(q(a[3]) - q(b[3])) < a[4] - 1e-6:
                da = abs((a[0] - b[0] + math.pi) % (2 * math.pi) - math.pi) * prof(q(a[3]))
                assert da >= (a[1] + b[1]) / 2 + a[6], (style, a, b)


@pytest.mark.parametrize("style", list(droop.STYLES))
def test_droop_never_reaches_the_bed_and_strands_are_at_most_4_layers(style):
    nz = printer.nozzle(0.4); S = SHAPES["cup"]; v = S.defaults(); prof = S.profile(v)[0]
    spots = droop._rows(style, prof, v["height"], nz, 1.0, 1.4)
    assert all(z - bu > 2.0 for _, _, bu, z, _, _, _ in spots)
    assert all(hh <= 4 * nz.layer_h + 1e-9 for *_, hh, _, _ in [(s[0], s[1], s[2], s[3], s[4], s[5], s[6]) for s in spots])


def test_strands_are_one_extrusion_except_swag():
    for style, sp in droop._SPEC.items():
        assert sp["width"] < 2 or style == "swag"


def test_droop_slicer_settings_keep_strands_molten():
    b = build.make("cup", "fringe", SMALL["cup"])
    o, f = b.overrides, b.per_filament
    assert set(o["enable_overhang_speed"]) == {"0"} and f["fan_max_speed"] == ["20"]
    base = printer.base_config(0.4)["nozzle_temperature"][0]
    assert int(f["nozzle_temperature"][0]) == int(base) + 5


def test_candle_holder_is_solid_with_infill_and_a_socket():
    b = build.make("candle", "curls", SMALL["candle"])
    m = b.parts[0][1]
    top = m.bounds[1][2]
    assert b.overrides["sparse_infill_density"] == "15%"
    assert not m.contains([[0, 0, top - 5]])[0]                 # the socket is open at the top
