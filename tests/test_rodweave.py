"""Woven rod lattice library: beads are printable solids, every pattern yields them, the block keeps the laws."""
import math
import numpy as np
import pytest

from textures import rodweave as rw


def test_bead_is_watertight_with_outward_normals():
    m = rw.straight([0, 0, 0.4], [20, 0, 0.4])
    assert m.is_watertight and m.volume > 0
    assert np.allclose(m.extents, [20 + rw.ROD["rw"] - 0.34, rw.ROD["rw"], rw.ROD["rh"]], atol=0.4)


def test_curved_bead_is_watertight():
    a = np.linspace(0, np.pi, 20)
    m = rw.bead(np.column_stack([10 * np.cos(a), 10 * np.sin(a), np.full(20, 0.4)]))
    assert m.is_watertight and m.volume > 0


@pytest.mark.parametrize("name", sorted(rw.PATTERNS))
def test_every_pattern_yields_printable_rods_inside_the_outline(name):
    outline = rw.Circle(40) if name == "polar" else rw.RoundedSquare(40, 8)
    rods = rw.PATTERNS[name](outline, 3.2)
    assert rods, name
    for m, col in rods:
        assert col in rw.SLOT
        assert m.is_watertight and m.volume > 0
        assert m.bounds[0][2] >= -1e-6                     # nothing below the bed
        assert np.abs(m.vertices[:, :2]).max() <= 20 + rw.ROD["rw"]   # stays inside the 40 mm outline (+ bead)


def test_block_has_flat_full_bottom_and_never_steps_outward():
    a, b = rw.block(size=40, height=8, floor_t=2.4, corner_r=8, dip_d=28, ease_top_r=3, twill_skip=4)
    both = np.vstack([a.vertices, b.vertices])
    rh = rw.ROD["rh"]
    reach = []
    for i in range(int(round(both[:, 2].max() / rh))):
        sl = both[(both[:, 2] >= i * rh - 1e-6) & (both[:, 2] <= (i + 1) * rh + 1e-6)]
        reach.append(np.abs(sl[:, :2]).max())
    assert reach[0] >= 20 - rw.ROD["rw"]                     # first course is the full footprint
    assert all(r2 <= r1 + 1e-3 for r1, r2 in zip(reach, reach[1:]))   # no course reaches past the one below


def test_group_by_colour_one_part_per_colour():
    rods = rw.PATTERNS["kagome"](rw.RoundedSquare(30, 6), 2.4)
    parts = rw.group_by_colour(rods)
    assert [p[2] for p in parts] == sorted({rw.SLOT[c] for _, c in rods})
    assert all(p[1].is_watertight for p in parts)
