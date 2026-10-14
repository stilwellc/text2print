"""Mix: bands of wall textures on one vessel."""
import numpy as np
import pytest

from text2print import build, compose, printer
from text2print.shapes import SHAPES

SMALL = {"cup": {"diameter": 60, "height": 50}, "vase": {"diameter": 80, "height": 80},
         "bowl": {"diameter": 100, "height": 40}, "goblet": {"diameter": 90, "height": 90}}


@pytest.mark.full
@pytest.mark.parametrize("shape", list(SMALL))
@pytest.mark.parametrize("preset", list(compose.PRESETS))
def test_presets_build_watertight_parts(shape, preset):
    b = build.make(shape, "mix", SMALL[shape], options={"bands": compose.PRESETS[preset]["bands"]})
    assert all(m.is_watertight and m.volume > 0 for _, m, _, _ in b.parts)
    assert (b.preview is not None) == bool(b.stats.get("strands"))


@pytest.mark.full
def test_every_mixable_texture_can_sit_between_two_others():
    for t in compose.MIXABLE:
        bands = [dict(texture="plain", share=30, slot=0), dict(texture=t, share=40, slot=1, slot2=0),
                 dict(texture="wave", share=30, slot=0)]
        b = build.make("cup", "mix", SMALL["cup"], options={"bands": bands})
        assert all(m.is_watertight for _, m, _, _ in b.parts), t


def test_same_colour_bands_merge_and_changes_happen_at_edges():
    one = build.make("cup", "mix", SMALL["cup"], options={"bands": [dict(texture="plain", share=50, slot=0),
                                                                    dict(texture="zigzag", share=50, slot=0)]})
    assert one.stats["colours"] == 1 and one.stats["swaps"] == 0
    assert len(one.parts[0][1].split(only_watertight=False)) == 1       # unioned across the band edge
    two = build.make("cup", "mix", SMALL["cup"], options={"bands": [dict(texture="plain", share=50, slot=0),
                                                                    dict(texture="zigzag", share=50, slot=1)]})
    assert two.stats["colours"] == 2 and two.stats["swaps"] == 1


def test_bands_keep_their_height_order_and_floor():
    nz = printer.nozzle(0.4); S = SHAPES["cup"]
    parts, prev, info = compose.build(S, S.resolve(SMALL["cup"]), nz,
                                      [dict(texture="plain", share=1, slot=0), dict(texture="plain", share=1, slot=1)])
    lo, hi = parts[0].bounds, parts[1].bounds
    assert lo[0][2] == pytest.approx(0) and hi[0][2] == pytest.approx(lo[1][2]) and hi[1][2] == pytest.approx(50, abs=0.2)


def test_droop_band_gets_droop_cooling_on_its_own_filament():
    b = build.make("cup", "mix", SMALL["cup"], options={"bands": compose.PRESETS["skirt"]["bands"]})
    assert "20" in b.per_filament["fan_max_speed"] and "100" in b.per_filament["fan_max_speed"] and b.stats["strands"] > 0


def test_mix_is_offered_only_on_wall_shapes():
    assert build.compatible("vase", "mix") and not build.compatible("tray", "mix") and not build.compatible("candle", "mix")
