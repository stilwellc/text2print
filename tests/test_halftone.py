"""The halftone family: complementary ribs, overhang law, settings."""
import numpy as np
import pytest

from text2print import build, halftone, printer
from text2print.shapes import SHAPES


@pytest.mark.full
@pytest.mark.parametrize("shape", ["cup", "vase", "bowl", "goblet"])
@pytest.mark.parametrize("pic", list(halftone.PICTURES))
def test_builds_two_watertight_parts(shape, pic):
    b = build.make(shape, "halftone", {"height": 40} if shape != "bowl" else {"height": 30}, nozzle=0.8,
                   options={"picture": pic})
    assert len(b.parts) == 2 and all(m.is_watertight and m.volume > 0 for _, m, _, _ in b.parts)


def test_layers_alternate_and_ribs_are_complementary():
    nz = printer.nozzle(0.8); S = SHAPES["cup"]; v = {"diameter": 80, "height": 30}
    parts, info = halftone.build(S, S.resolve(v), nz, "fade")
    lh = info["layer_h"]; z0 = info["floor_layers"] * lh
    a = parts[0].section(plane_origin=[0, 0, z0 + 2.5 * lh], plane_normal=[0, 0, 1])     # a colour-A layer? (k odd)
    b = parts[1].section(plane_origin=[0, 0, z0 + 2.5 * lh], plane_normal=[0, 0, 1])
    assert (a is None) != (b is None)                                                      # exactly one colour per layer


@pytest.mark.parametrize("nozzle", printer.NOZZLES)
def test_settings_follow_the_recipe(nozzle):
    b = build.make("cup", "halftone", {"height": 30}, nozzle=nozzle)
    lh, lw = halftone.RECIPE[nozzle]
    assert b.overrides["layer_height"] == f"{lh:.2f}" and b.overrides["outer_wall_line_width"] == f"{lw:.2f}"
    assert b.overrides["wall_loops"] == "1" and b.stats["layer_h"] == lh
    assert lh == pytest.approx(float(printer.base_config(nozzle)["max_layer_height"][0]))


def test_swing_respects_the_overhang_law():
    nz = printer.nozzle(0.4); S = SHAPES["bowl"]; v = S.defaults()
    parts, info = halftone.build(S, v, nz, "fade")
    lw = info["line_w"]; prof = S.profile(v)[0]
    for m in parts.values():
        V = m.vertices; r = np.hypot(V[:, 0], V[:, 1])
        outer = r - np.array([prof(z) for z in V[:, 2]])
        assert outer.max() <= 0.6 * lw + 0.3                       # profile sampling slack


def test_band_two_halves_the_changes():
    one = build.make("cup", "halftone", {"height": 40}, nozzle=0.8)
    two = build.make("cup", "halftone", {"height": 40}, nozzle=0.8, options={"band": "2"})
    assert abs(two.stats["swaps"] * 2 - one.stats["swaps"]) <= 1
