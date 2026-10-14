"""The woven rod lattice: printable beads, every shape x pattern, and the print-verified laws."""
import math

import numpy as np
import pytest

from text2print import build, lattice, printer
from text2print.shapes import SHAPES

NZ = printer.nozzle(0.4)
SMALL = {"tray": {"width": 60, "height": 12, "dish": 36, "floor": 4},
         "platter": {"width": 100, "height": 10, "dish": 70, "floor": 3},
         "dish": {"diameter": 60, "height": 12, "dish": 40, "floor": 4},
         "coaster": {"width": 70, "height": 6, "dish": 50, "floor": 4},
         "cup": {"diameter": 50, "height": 30, "wall": 6, "floor": 3},
         "shade": {"diameter": 80, "height": 60, "wall": 5}}


def test_straight_beads_are_watertight_and_outward():
    m = lattice.straight_beads([[0, 0, 0.4], [0, 5, 0.4]], [[20, 0, 0.4], [0, 25, 0.4]], NZ.rod_w, NZ.rod_h)
    assert m.is_watertight and m.volume > 0
    assert np.isclose(m.bounds[1][2] - m.bounds[0][2], NZ.rod_h, atol=1e-6)


def test_path_bead_is_watertight_and_outward():
    a = np.linspace(0, math.pi, 30)
    m = lattice.path_bead(np.column_stack([10 * np.cos(a), 10 * np.sin(a), np.full(30, 0.4)]), NZ.rod_w, NZ.rod_h)
    assert m.is_watertight and m.volume > 0


@pytest.mark.parametrize("shape,pattern", [(s, p) for s in SMALL for p in lattice.PATTERNS if build.compatible(s, p)])
def test_every_shape_and_pattern_builds_printable_parts(shape, pattern):
    b = build.make(shape, pattern, SMALL[shape])
    assert b.parts
    for _, m, slot, _ in b.parts:
        assert m.is_watertight and m.volume > 0
        assert m.bounds[0][2] >= -1e-6                                     # nothing below the bed
    half = max(np.abs(m.bounds[:, :2]).max() for _, m, _, _ in b.parts)
    size = SMALL[shape].get("width", SMALL[shape].get("diameter"))
    assert half <= size / 2 + 0.05                                         # never past the outline


@pytest.mark.parametrize("shape", list(SMALL))
def test_flat_full_bottom_and_no_outward_steps(shape):
    """Collin's law: the first course is the full footprint and no course reaches past the one below it."""
    b = build.make(shape, "grid", SMALL[shape])
    V = np.vstack([m.vertices for _, m, _, _ in b.parts])
    reach = []
    for i in range(int(round(V[:, 2].max() / NZ.rod_h))):
        band = V[(V[:, 2] >= i * NZ.rod_h - 1e-6) & (V[:, 2] <= (i + 1) * NZ.rod_h + 1e-6)]
        reach.append(np.hypot(band[:, 0], band[:, 1]).max() if SHAPES[shape].round else np.abs(band[:, :2]).max())
    size = SMALL[shape].get("width", SMALL[shape].get("diameter"))
    assert reach[0] >= size / 2 - NZ.pitch
    assert all(r2 <= r1 + 0.05 for r1, r2 in zip(reach, reach[1:]))


def test_default_tray_twill_is_the_printed_tray():
    """The Oct 2026 print: 117 mm tray, twill, 41 courses, ~1,627 rods of 1.68 x 0.80 on a 3.6 pitch,
    100.0 cm3 of rods (the STL that printed)."""
    b = build.make("tray", "twill")
    assert (b.stats["courses"], b.stats["pitch"], b.stats["rod"]) == (41, 3.6, "1.68 × 0.80 mm")
    assert abs(b.stats["rods"] - 1627) <= 10
    assert b.stats["size"] == [117.0, 117.0, 32.8]
    assert sum(m.volume for _, m, _, _ in b.parts) / 1000 == pytest.approx(100.0, rel=0.02)


def test_swaps_once_per_course_and_merge_when_colours_match():
    b = build.make("coaster", "grid", SMALL["coaster"])
    assert b.stats["swaps"] == b.stats["courses"] - 1
    one = build.make("coaster", "grid", SMALL["coaster"], colours=["#8B3A2F", "#8B3A2F"])
    assert one.stats["colours"] == 1 and one.stats["swaps"] == 0
    mixed = build.make("coaster", "tartan", SMALL["coaster"])
    assert mixed.stats["swaps"] > 2 * b.stats["swaps"]                      # tartan mixes colours inside a course


def test_selvedge_loops_stay_inside_the_outline():
    b = build.make("tray", "selvedge", SMALL["tray"])
    assert max(np.abs(m.bounds[:, :2]).max() for _, m, _, _ in b.parts) <= 30.05


def test_polar_needs_a_round_shape():
    assert build.compatible("dish", "polar") and not build.compatible("tray", "polar")
    with pytest.raises(ValueError):
        build.make("tray", "polar")
